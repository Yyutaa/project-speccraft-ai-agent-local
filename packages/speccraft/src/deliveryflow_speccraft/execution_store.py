"""SQLite task ownership. Application use cases still decide legal domain transitions."""

from hashlib import sha256
from typing import Literal
from uuid import uuid4

from deliveryflow_contracts.execution import ModelCallRecord, ModelJob, ProviderBinding
from deliveryflow_contracts.model_tasks import ModelTaskInput, QualityTaskData
from deliveryflow_contracts.quality import QualityCycleRequest
from deliveryflow_contracts.runs import AvailableCommand, RunResponse

from deliveryflow_speccraft.model_boundary import validate_task_input
from deliveryflow_speccraft.persistence import RunStore


def run_digest(run: RunResponse) -> str:
    return sha256(run.model_dump_json().encode()).hexdigest()


class ExecutionStore(RunStore):
    """One active task per Run, fenced writes and short transactions only."""

    def bind_provider(self, run_id: str, binding: ProviderBinding) -> None:
        binding = ProviderBinding.model_validate(binding.model_dump())
        with self._write_scope():
            self.snapshot(run_id)
            row = self._connection.execute(
                "SELECT payload FROM run_provider_bindings WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row:
                if ProviderBinding.model_validate_json(row[0]) != binding:
                    raise ValueError("provider_binding_conflict")
                return
            self._connection.execute(
                "INSERT INTO run_provider_bindings VALUES (?,?)",
                (run_id, binding.model_dump_json()),
            )
            self._event(run_id, "provider.bound")

    def get_provider_binding(self, run_id: str) -> ProviderBinding:
        with self._mutex:
            row = self._connection.execute(
                "SELECT payload FROM run_provider_bindings WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ValueError("provider_binding_missing")
        return ProviderBinding.model_validate_json(row[0])

    def enqueue_command_task(
        self,
        run_id: str,
        command_id: str,
        kind: AvailableCommand,
        payload: dict[str, object],
        task: ModelTaskInput,
        *,
        expected_version: int,
        committed_run: RunResponse | None = None,
        actor_claim: str | None = None,
        rationale: str | None = None,
        quality_request: QualityCycleRequest | None = None,
    ) -> ModelJob:
        task = validate_task_input(task)
        if quality_request is not None:
            quality_request = QualityCycleRequest.model_validate(quality_request.model_dump())
            if task.task_kind != "td_quality" or not isinstance(task.payload, QualityTaskData):
                raise ValueError("quality_job_task_conflict")
            if task.payload.mode != "discover" or task.payload.run_id != run_id:
                raise ValueError("quality_job_task_conflict")
        with self._write_scope():
            self.get_provider_binding(run_id)
            self.model_budget(run_id)  # Old Runs cannot acquire invented resource history.
            # Include the task binding in the digest so the same command cannot hide a new task.
            self.accept_command(
                run_id,
                command_id,
                kind,
                {
                    "command": payload,
                    "task_binding": task.input_binding,
                    **(
                        {"quality_request": quality_request.model_dump(mode="json")}
                        if quality_request
                        else {}
                    ),
                },
                expected_version=expected_version,
                actor_claim=actor_claim,
                rationale=rationale,
            )
            if self._connection.execute(
                "SELECT 1 FROM model_jobs WHERE run_id=? AND status IN ('queued','running')",
                (run_id,),
            ).fetchone():
                raise ValueError("run_execution_busy")
            if committed_run is not None:
                if committed_run.run_id != run_id:
                    raise ValueError("run_identity_conflict")
                self[run_id] = committed_run
                self.commands[run_id].add(command_id)
                self.mark_command_committed(run_id, command_id)
            job = ModelJob(
                job_id=str(uuid4()),
                run_id=run_id,
                command_id=command_id,
                task=task,
                quality_request=quality_request,
                baseline_hash=run_digest(self[run_id]),
            )
            self._connection.execute(
                "INSERT INTO model_jobs("
                "job_id,run_id,command_id,task,baseline_hash,status,created_at,quality_request) "
                "VALUES (?,?,?,?,?,'queued',?,?)",
                (
                    job.job_id,
                    run_id,
                    command_id,
                    task.model_dump_json(),
                    job.baseline_hash,
                    job.created_at.isoformat(),
                    quality_request.model_dump_json() if quality_request else None,
                ),
            )
            self._event(run_id, "job.queued")
            return job

    def job_for_command(self, run_id: str, command_id: str) -> ModelJob | None:
        with self._mutex:
            row = self._connection.execute(
                "SELECT job_id FROM model_jobs WHERE run_id=? AND command_id=?",
                (run_id, command_id),
            ).fetchone()
            return self.get_job(row[0]) if row else None

    def get_job(self, job_id: str) -> ModelJob:
        with self._mutex:
            row = self._connection.execute(
                "SELECT job_id,run_id,command_id,task,baseline_hash,status,epoch,owner,lease_until,"
                "created_at,error_code,quality_request FROM model_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return ModelJob(
            job_id=row[0],
            run_id=row[1],
            command_id=row[2],
            task=ModelTaskInput.model_validate_json(row[3]),
            baseline_hash=row[4],
            status=row[5],
            epoch=row[6],
            owner=row[7],
            lease_until=row[8],
            created_at=row[9],
            error_code=row[10],
            quality_request=QualityCycleRequest.model_validate_json(row[11]) if row[11] else None,
        )

    def jobs_for_run(self, run_id: str) -> tuple[ModelJob, ...]:
        with self._mutex:
            ids = self._connection.execute(
                "SELECT job_id FROM model_jobs WHERE run_id=? ORDER BY rowid",
                (run_id,),
            ).fetchall()
            return tuple(self.get_job(row[0]) for row in ids)

    def _now(self) -> float:
        # Same SQLite clock for all local processes; no client timestamp controls ownership.
        return float(
            self._connection.execute("SELECT (julianday('now') - 2440587.5) * 86400.0").fetchone()[
                0
            ]
        )

    def claim_next(self, owner: str, *, lease_seconds: int = 30) -> ModelJob | None:
        if not owner.strip() or len(owner) > 128 or not 1 <= lease_seconds <= 120:
            raise ValueError("invalid_execution_owner")
        with self._write_scope():
            now = self._now()
            row = self._connection.execute(
                "SELECT job_id FROM model_jobs WHERE status='queued' "
                "OR (status='running' AND lease_until<=?) ORDER BY rowid LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            previous = self.get_job(row[0])
            # Expired work may have reached the provider. Never refund or claim it never ran.
            for call in self.model_calls(previous.run_id):
                if call.command_id == previous.command_id and call.status == "reserved":
                    self.finish_model_call(call.call_id, "interrupted")
            self._connection.execute(
                "UPDATE model_jobs SET status='running',epoch=epoch+1,owner=?,lease_until=? "
                "WHERE job_id=?",
                (owner, now + lease_seconds, previous.job_id),
            )
            self._event(previous.run_id, "job.claimed")
            return self.get_job(previous.job_id)

    def require_lease(self, lease: ModelJob, *, check_input: bool = True) -> ModelJob:
        current = self.get_job(lease.job_id)
        if (
            current.status != "running"
            or current.owner != lease.owner
            or current.epoch != lease.epoch
            or current.lease_until is None
            or current.lease_until <= self._now()
        ):
            raise ValueError("execution_lease_lost")
        if check_input and current.baseline_hash != run_digest(self[current.run_id]):
            raise ValueError("execution_input_stale")
        return current

    def renew_lease(self, lease: ModelJob, *, lease_seconds: int = 30) -> ModelJob:
        if not 1 <= lease_seconds <= 120:
            raise ValueError("invalid_execution_lease")
        with self._write_scope():
            current = self.require_lease(lease, check_input=False)
            self._connection.execute(
                "UPDATE model_jobs SET lease_until=? WHERE job_id=?",
                (self._now() + lease_seconds, current.job_id),
            )
            # Heartbeats do not invalidate REST caches or produce notification storms.
            return self.get_job(current.job_id)

    def reserve_job_call(
        self,
        lease: ModelJob,
        *,
        task: ModelTaskInput | None = None,
    ) -> ModelCallRecord:
        with self._write_scope():
            current = self.require_lease(lease)
            attempts = [
                c for c in self.model_calls(current.run_id) if c.command_id == current.command_id
            ]
            actual = validate_task_input(task or current.task)
            limit = self.get_provider_binding(current.run_id).max_attempts
            if current.quality_request:
                if (
                    actual.task_kind != "td_quality"
                    or not isinstance(actual.payload, QualityTaskData)
                    or actual.payload.run_id != current.run_id
                    or actual.resources != current.task.resources
                ):
                    raise ValueError("quality_job_task_conflict")
                limit *= 2 + 2 * current.quality_request.max_steps
            elif actual != current.task:
                raise ValueError("execution_input_stale")
            if len(attempts) >= limit:
                raise ValueError("job_model_budget_exhausted")
            return self.reserve_model_call(
                current.run_id,
                current.command_id,
                actual.input_binding,
                actual.task_kind,
            )

    def finish_job_call(
        self,
        lease: ModelJob,
        call_id: str,
        status: Literal["succeeded", "failed"],
    ) -> None:
        with self._write_scope():
            current = self.require_lease(lease, check_input=False)
            if not any(
                c.call_id == call_id and c.command_id == current.command_id
                for c in self.model_calls(current.run_id)
            ):
                raise ValueError("model_call_identity_conflict")
            self.finish_model_call(call_id, status)

    def complete_job(self, lease: ModelJob, run: RunResponse) -> ModelJob:
        run = RunResponse.model_validate(run.model_dump())
        with self._write_scope():
            current = self.require_lease(lease)
            if run.run_id != current.run_id:
                raise ValueError("run_identity_conflict")
            self[current.run_id] = run
            receipt = self.get_command(current.run_id, current.command_id)
            if current.command_id not in self.commands[current.run_id]:
                self.commands[current.run_id].add(current.command_id)
            elif not receipt.domain_committed:
                raise ValueError("duplicate_command")
            self.mark_command_committed(current.run_id, current.command_id)
            self.finish_command(current.run_id, current.command_id, "succeeded")
            self._terminal(current, "succeeded")
            return self.get_job(current.job_id)

    def fail_job(self, lease: ModelJob, code: str) -> ModelJob:
        with self._write_scope():
            current = self.require_lease(lease, check_input=False)
            self.finish_command(current.run_id, current.command_id, "failed", error_code=code)
            self._terminal(current, "failed", code)
            return self.get_job(current.job_id)

    def cancel_job(self, job_id: str) -> ModelJob:
        with self._write_scope():
            current = self.get_job(job_id)
            if current.status not in ("queued", "running"):
                raise ValueError("execution_already_finished")
            self.finish_command(current.run_id, current.command_id, "cancelled")
            self._terminal(current, "cancelled")
            self._event(current.run_id, "job.cancelled")
            return self.get_job(current.job_id)

    def _terminal(
        self,
        current: ModelJob,
        status: Literal["succeeded", "failed", "cancelled"],
        code: str | None = None,
    ) -> None:
        for call in self.model_calls(current.run_id):
            if call.command_id == current.command_id and call.status == "reserved":
                self.finish_model_call(call.call_id, "interrupted")
        self._connection.execute(
            "UPDATE model_jobs SET status=?,owner=NULL,lease_until=NULL,epoch=epoch+1,error_code=? "
            "WHERE job_id=?",
            (status, code, current.job_id),
        )
        self._event(current.run_id, "job.finished")

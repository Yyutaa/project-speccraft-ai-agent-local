"""Managed commands and leased model jobs, separated by explicit human Gates."""

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from uuid import uuid4

from deliveryflow_contracts.execution import (
    ManagedClarificationRequest,
    ManagedJobControlRequest,
    ManagedPrdApprovalRequest,
    ManagedRunAcceptance,
    ManagedTechnicalDecisionsRequest,
    ModelJob,
    ProviderBinding,
)
from deliveryflow_contracts.facts import ClarificationBatch
from deliveryflow_contracts.model_tasks import ClarificationTaskData, PrdTaskData
from deliveryflow_contracts.prd import PrdRevision
from deliveryflow_contracts.runs import AvailableCommand, CreateRunRequest, RunStatus

from deliveryflow_speccraft.execution import invoke_job_model
from deliveryflow_speccraft.model_boundary import ModelBoundaryError, build_clarification_task
from deliveryflow_speccraft.model_provider import BoundModelProvider, ProviderError
from deliveryflow_speccraft.persistence import ModelBudgetError
from deliveryflow_speccraft.prd import check_prd_readiness
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    GovernanceError,
    InvalidClarification,
    InvalidRunTransition,
    InvalidTechnicalDecision,
    PrdNotReady,
    RevisionConflict,
    RunRunner,
)


@contextmanager
def _command_errors() -> Iterator[None]:
    try:
        yield
    except InvalidRunTransition:
        raise GovernanceError("invalid_run_transition", 409) from None
    except ContentHashConflict:
        raise GovernanceError("content_hash_conflict", 409) from None
    except RevisionConflict:
        raise GovernanceError("revision_conflict", 409) from None
    except PrdNotReady:
        raise GovernanceError("prd_not_ready", 409) from None
    except InvalidTechnicalDecision:
        raise GovernanceError("invalid_technical_decision", 422) from None
    except InvalidClarification:
        raise GovernanceError("invalid_clarification", 422) from None
    except ValueError as error:
        if str(error) in {
            "duplicate_command",
            "command_payload_conflict",
            "run_version_conflict",
            "run_execution_busy",
            "provider_binding_missing",
            "execution_input_stale",
        }:
            raise GovernanceError(str(error), 409) from None
        raise


class ManagedRunService:
    def __init__(self, runner: RunRunner, binding: ProviderBinding | None = None) -> None:
        self.runner = runner
        self.binding = binding

    def create_run(self, request: CreateRunRequest) -> ManagedRunAcceptance:
        if self.binding is None:
            raise GovernanceError("provider_binding_missing", 409)
        run = self.runner.prepare_run(request, defer_clarification=True)
        run = self.runner._validated_update(
            run, {"quality_provider": f"{self.binding.provider}:{self.binding.model}"}
        )
        store = self.runner._runs
        command_id = str(uuid4())
        task = build_clarification_task(run.completeness.gaps)
        with store:
            self.runner.persist_prepared_run(run)
            store.bind_provider(run.run_id, self.binding)
            job = store.enqueue_command_task(
                run.run_id,
                command_id,
                AvailableCommand.CREATE_RUN,
                {"governance_contract_version": 2},
                task,
                expected_version=store.snapshot(run.run_id).run_version,
            )
            receipt = store.get_command(run.run_id, command_id)
        return ManagedRunAcceptance(
            run_id=run.run_id,
            command_id=command_id,
            job_id=job.job_id,
            receipt=receipt,
        )

    def submit_clarification(
        self, run_id: str, command: ManagedClarificationRequest
    ) -> ManagedRunAcceptance:
        command = ManagedClarificationRequest.model_validate(command.model_dump())
        store = self.runner._runs
        request = command.request
        payload = request.model_dump(mode="json")
        with _command_errors(), store._write_scope():
            current = store.snapshot(run_id)
            if not self.runner.is_managed_run(run_id):
                raise GovernanceError("execution_mode_conflict", 409)
            prior = store.job_for_command(run_id, request.command_id)
            if prior is not None:
                # Replay comparison uses the originally frozen task, never a newly rebuilt task.
                store.accept_command(
                    run_id,
                    request.command_id,
                    AvailableCommand.SUBMIT_CLARIFICATION,
                    {"command": payload, "task_binding": prior.task.input_binding},
                    expected_version=command.expected_run_version,
                )
            if current.run_version != command.expected_run_version:
                raise ValueError("run_version_conflict")
            preparing = self.runner.prepare_clarification(current.run, request)
            task = self.runner.prepare_prd_task(preparing.ledger)
            job = store.enqueue_command_task(
                run_id,
                request.command_id,
                AvailableCommand.SUBMIT_CLARIFICATION,
                payload,
                task,
                expected_version=command.expected_run_version,
                committed_run=preparing,
                actor_claim=request.actor_claim,
                rationale=request.rationale,
            )
            return ManagedRunAcceptance(
                run_id=run_id,
                command_id=request.command_id,
                job_id=job.job_id,
                receipt=store.get_command(run_id, request.command_id),
            )

    def approve_prd(self, run_id: str, command: ManagedPrdApprovalRequest) -> ManagedRunAcceptance:
        command = ManagedPrdApprovalRequest.model_validate(command.model_dump())
        store = self.runner._runs
        with _command_errors(), store._write_scope():
            snapshot = store.snapshot(run_id)
            if not self.runner.is_managed_run(run_id):
                raise GovernanceError("execution_mode_conflict", 409)
            self._check_replay(
                run_id,
                command.command_id,
                AvailableCommand.APPROVE_PRD,
                command.request.model_dump(mode="json"),
                command.expected_run_version,
            )
            preparing = self.runner.prepare_prd_approval(snapshot.run, command.request)
            task = self.runner.prepare_td_task(preparing)
            job = store.enqueue_command_task(
                run_id,
                command.command_id,
                AvailableCommand.APPROVE_PRD,
                command.request.model_dump(mode="json"),
                task,
                expected_version=command.expected_run_version,
                committed_run=preparing,
                actor_claim=command.request.actor,
                rationale=command.request.rationale,
            )
            return ManagedRunAcceptance(
                run_id=run_id,
                command_id=command.command_id,
                job_id=job.job_id,
                receipt=store.get_command(run_id, command.command_id),
            )

    def submit_technical_decisions(
        self, run_id: str, command: ManagedTechnicalDecisionsRequest
    ) -> ManagedRunAcceptance:
        command = ManagedTechnicalDecisionsRequest.model_validate(command.model_dump())
        if any(decision.actor != command.actor_claim for decision in command.request.decisions):
            raise GovernanceError("command_identity_conflict", 422)
        store = self.runner._runs
        with _command_errors(), store._write_scope():
            snapshot = store.snapshot(run_id)
            if not self.runner.is_managed_run(run_id):
                raise GovernanceError("execution_mode_conflict", 409)
            self._check_replay(
                run_id,
                command.command_id,
                AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,
                command.model_dump(mode="json"),
                command.expected_run_version,
            )
            preparing = self.runner.prepare_technical_decisions(snapshot.run, command.request)
            task = self.runner.prepare_td_task(preparing)
            job = store.enqueue_command_task(
                run_id,
                command.command_id,
                AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,
                command.model_dump(mode="json"),
                task,
                expected_version=command.expected_run_version,
                committed_run=preparing,
                actor_claim=command.actor_claim,
                rationale=command.rationale,
            )
            return ManagedRunAcceptance(
                run_id=run_id,
                command_id=command.command_id,
                job_id=job.job_id,
                receipt=store.get_command(run_id, command.command_id),
            )

    def _check_replay(
        self,
        run_id: str,
        command_id: str,
        kind: AvailableCommand,
        payload: dict[str, object],
        version: int,
    ) -> None:
        store = self.runner._runs
        prior = store.job_for_command(run_id, command_id)
        if prior is not None:
            store.accept_command(
                run_id,
                command_id,
                kind,
                {"command": payload, "task_binding": prior.task.input_binding},
                expected_version=version,
            )
        if store.snapshot(run_id).run_version != version:
            raise ValueError("run_version_conflict")

    def retry_job(
        self, run_id: str, job_id: str, command: ManagedJobControlRequest
    ) -> ManagedRunAcceptance:
        command = ManagedJobControlRequest.model_validate(command.model_dump())
        store = self.runner._runs
        payload = {"target_job_id": job_id, **command.model_dump(mode="json")}
        with _command_errors(), store._write_scope():
            snapshot = store.snapshot(run_id)
            if not self.runner.is_managed_run(run_id):
                raise GovernanceError("execution_mode_conflict", 409)
            original = store.get_job(job_id)
            if original.run_id != run_id:
                raise KeyError(job_id)
            prior = store.job_for_command(run_id, command.command_id)
            if prior is not None:
                store.accept_command(
                    run_id,
                    command.command_id,
                    AvailableCommand.RETRY_EXECUTION,
                    {
                        "command": payload,
                        "task_binding": prior.task.input_binding,
                        **(
                            {"quality_request": prior.quality_request.model_dump(mode="json")}
                            if prior.quality_request
                            else {}
                        ),
                    },
                    expected_version=command.expected_run_version,
                )
            if snapshot.run_version != command.expected_run_version:
                raise ValueError("run_version_conflict")
            summary = self.runner.project_job_summary(snapshot, original)
            if AvailableCommand.RETRY_EXECUTION not in summary.available_commands:
                raise GovernanceError("execution_control_unavailable", 409)
            job = store.enqueue_command_task(
                run_id,
                command.command_id,
                AvailableCommand.RETRY_EXECUTION,
                payload,
                original.task,
                expected_version=command.expected_run_version,
                actor_claim=command.actor_claim,
                rationale=command.rationale,
                quality_request=original.quality_request.model_copy(
                    update={
                        "command_id": command.command_id,
                        "actor_claim": command.actor_claim,
                    }
                )
                if original.quality_request
                else None,
            )
            return ManagedRunAcceptance(
                run_id=run_id,
                command_id=command.command_id,
                job_id=job.job_id,
                receipt=store.get_command(run_id, command.command_id),
            )

    def cancel_job(
        self, run_id: str, job_id: str, command: ManagedJobControlRequest
    ) -> ManagedRunAcceptance:
        command = ManagedJobControlRequest.model_validate(command.model_dump())
        store = self.runner._runs
        with _command_errors(), store._write_scope():
            snapshot = store.snapshot(run_id)
            if not self.runner.is_managed_run(run_id):
                raise GovernanceError("execution_mode_conflict", 409)
            job = store.get_job(job_id)
            if job.run_id != run_id:
                raise KeyError(job_id)
            store.accept_command(
                run_id,
                command.command_id,
                AvailableCommand.CANCEL_EXECUTION,
                {"target_job_id": job_id, **command.model_dump(mode="json")},
                expected_version=command.expected_run_version,
                actor_claim=command.actor_claim,
                rationale=command.rationale,
            )
            summary = self.runner.project_job_summary(snapshot, job)
            if AvailableCommand.CANCEL_EXECUTION not in summary.available_commands:
                raise GovernanceError("execution_control_unavailable", 409)
            store.cancel_job(job_id)
            store.commands[run_id].add(command.command_id)
            store.mark_command_committed(run_id, command.command_id)
            receipt = store.finish_command(run_id, command.command_id, "succeeded")
            return ManagedRunAcceptance(
                run_id=run_id,
                command_id=command.command_id,
                job_id=job_id,
                receipt=receipt,
            )


def execute_model_job(
    runner: RunRunner,
    provider: BoundModelProvider,
    *,
    owner: str,
    claimed: ModelJob | None = None,
) -> ModelJob | None:
    """Execute one leased model job; domain guards retain all approval authority."""
    store = runner._runs
    lease = claimed if claimed is not None else store.claim_next(owner)
    if lease is None:
        return None
    if lease.task.task_kind == "td_quality":
        from deliveryflow_speccraft.managed_quality import execute_quality_job

        return execute_quality_job(runner, provider, lease)

    def failed(code: str) -> ModelJob:
        try:
            return store.fail_job(lease, code)
        except ValueError as error:
            if str(error) == "execution_lease_lost":
                return store.get_job(lease.job_id)
            raise

    try:
        store.require_lease(lease)
        run = runner.get_run(lease.run_id)
        if lease.task.task_kind == "clarification":
            if (
                not isinstance(lease.task.payload, ClarificationTaskData)
                or run.status is not RunStatus.CONTEXT_PREPARING
                or lease.task.payload.gaps != run.completeness.gaps
            ):
                return failed("execution_task_not_supported")
            result = invoke_job_model(store, lease, provider)
            batch = ClarificationBatch(
                batch_id=str(uuid4()),
                revision=1,
                ledger_revision=run.ledger.revision,
                gap_ids=tuple(g.gap_id for g in run.completeness.gaps),
                blocking_gap_ids=tuple(g.gap_id for g in run.completeness.gaps if g.blocking),
                proposals=result.proposals,
                required_candidate_ids=tuple(c.candidate_id for c in run.pending_source_claims),
            )
            candidate = runner._validated_update(
                run,
                {
                    "status": RunStatus.AWAITING_CLARIFICATION,
                    "clarification_batch": batch,
                    "available_commands": (AvailableCommand.SUBMIT_CLARIFICATION,),
                },
            )
        elif lease.task.task_kind == "prd_author":
            if (
                not isinstance(lease.task.payload, PrdTaskData)
                or run.status is not RunStatus.PRD_PREPARING
            ):
                return failed("execution_task_not_supported")
            expected = runner.prepare_prd_task(run.ledger)
            if expected.input_binding != lease.task.input_binding:
                return failed("execution_input_stale")
            result = invoke_job_model(store, lease, provider)
            assert result.content is not None
            prd = PrdRevision(
                revision=1,
                content=result.content,
                content_hash=sha256(result.content.encode()).hexdigest(),
            )
            candidate = runner.project_prd_preparation(
                run,
                lease.task.payload.blueprint,
                prd,
                check_prd_readiness(prd),
            )
        elif lease.task.task_kind == "td_author":
            if run.status is not RunStatus.TD_PREPARING:
                return failed("execution_task_not_supported")
            if runner.prepare_td_task(run).input_binding != lease.task.input_binding:
                return failed("execution_input_stale")
            result = invoke_job_model(store, lease, provider)
            candidate = runner.project_td_preparation(run, result)
        else:
            return failed("execution_task_not_supported")
        return store.complete_job(lease, candidate)
    except (ProviderError, ModelBoundaryError) as error:
        return failed(error.code)
    except ModelBudgetError as error:
        return failed(str(error))
    except ValueError as error:
        if str(error) == "execution_lease_lost":
            return store.get_job(lease.job_id)  # A cancelled/stolen task cannot write a failure.
        if str(error) in ("execution_input_stale", "job_model_budget_exhausted"):
            return failed(str(error))
        raise


# Preserve the first phase's Python entry point; the process now dispatches by task kind.
execute_clarification_job = execute_model_job

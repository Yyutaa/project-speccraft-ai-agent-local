"""First managed vertical: background clarification candidates, then an explicit human Gate."""

from uuid import uuid4

from deliveryflow_contracts.execution import ManagedRunAcceptance, ModelJob, ProviderBinding
from deliveryflow_contracts.facts import ClarificationBatch
from deliveryflow_contracts.model_tasks import ClarificationTaskData
from deliveryflow_contracts.runs import AvailableCommand, CreateRunRequest, RunStatus

from deliveryflow_speccraft.execution import invoke_job_model
from deliveryflow_speccraft.model_boundary import ModelBoundaryError, build_clarification_task
from deliveryflow_speccraft.model_provider import BoundModelProvider, ProviderError
from deliveryflow_speccraft.persistence import ModelBudgetError
from deliveryflow_speccraft.runner import RunRunner


class ManagedRunService:
    def __init__(self, runner: RunRunner, binding: ProviderBinding) -> None:
        self.runner = runner
        self.binding = binding

    def create_run(self, request: CreateRunRequest) -> ManagedRunAcceptance:
        run = self.runner.prepare_run(request, defer_clarification=True)
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


def execute_clarification_job(
    runner: RunRunner,
    provider: BoundModelProvider,
    *,
    owner: str,
    claimed: ModelJob | None = None,
) -> ModelJob | None:
    """Initial Worker scope. Other task kinds stay explicitly unsupported for this phase."""
    store = runner._runs
    lease = claimed if claimed is not None else store.claim_next(owner)
    if lease is None:
        return None

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
        if (
            lease.task.task_kind != "clarification"
            or not isinstance(lease.task.payload, ClarificationTaskData)
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

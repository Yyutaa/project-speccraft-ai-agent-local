"""Lease-fenced background quality batches; model audits never grant human approval."""

from deliveryflow_contracts.execution import ManagedQualityRequest, ManagedRunAcceptance, ModelJob
from deliveryflow_contracts.model_tasks import ModelResources, ModelTaskInput
from deliveryflow_contracts.runs import AvailableCommand, RunStatus

from deliveryflow_speccraft.execution import invoke_job_model
from deliveryflow_speccraft.managed import _command_errors
from deliveryflow_speccraft.model_boundary import ModelBoundaryError
from deliveryflow_speccraft.model_provider import BoundModelProvider, ProviderError
from deliveryflow_speccraft.persistence import ModelBudgetError
from deliveryflow_speccraft.quality_engine import QualityProviderError, execute_cycle, make_task
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    GovernanceError,
    RevisionConflict,
    RunRunner,
)


def resources(runner: RunRunner) -> ModelResources:
    return ModelResources(
        template=runner._td_pack.template,
        guide=runner._td_pack.guide,
        self_check=runner._td_pack.self_check,
    )


def submit_quality(
    runner: RunRunner, run_id: str, command: ManagedQualityRequest
) -> ManagedRunAcceptance:
    command = ManagedQualityRequest.model_validate(command.model_dump())
    store = runner._runs
    request = command.request
    payload = command.model_dump(mode="json")
    with _command_errors(), store._write_scope():
        snapshot = store.snapshot(run_id)
        if not runner.is_managed_run(run_id):
            raise GovernanceError("execution_mode_conflict", 409)
        prior = store.job_for_command(run_id, request.command_id)
        if prior:
            store.accept_command(
                run_id,
                request.command_id,
                AvailableCommand.RUN_TD_QUALITY,
                {
                    "command": payload,
                    "task_binding": prior.task.input_binding,
                    "quality_request": request.model_dump(mode="json"),
                },
                expected_version=command.expected_run_version,
            )
        run = snapshot.run
        if snapshot.run_version != command.expected_run_version:
            raise ValueError("run_version_conflict")
        binding = store.get_provider_binding(run_id)
        if run.quality_provider != f"{binding.provider}:{binding.model}":
            raise GovernanceError("quality_provider_unavailable", 409)
        if run.status != RunStatus.TD_AWAITING_APPROVAL or not run.td_draft:
            raise GovernanceError("invalid_run_transition", 409)
        if request.expected_td_revision != run.td_draft.revision:
            raise RevisionConflict("TD revision does not match")
        if request.expected_td_content_hash != run.td_draft.content_hash:
            raise ContentHashConflict("TD hash does not match")
        if not run.td_review or request.expected_review_revision != run.td_review.review_revision:
            raise GovernanceError("td_review_conflict", 409)
        usage = store.model_budget(run_id)
        if usage.model_calls >= usage.policy.max_model_calls:
            raise GovernanceError("run_model_budget_exhausted", 409)
        task = make_task(run, "discover", resources(runner))
        job = store.enqueue_command_task(
            run_id,
            request.command_id,
            AvailableCommand.RUN_TD_QUALITY,
            payload,
            task,
            expected_version=command.expected_run_version,
            actor_claim=request.actor_claim,
            rationale=command.rationale,
            quality_request=request,
        )
        return ManagedRunAcceptance(
            run_id=run_id,
            command_id=request.command_id,
            job_id=job.job_id,
            receipt=store.get_command(run_id, request.command_id),
        )


def execute_quality_job(
    runner: RunRunner, provider: BoundModelProvider, lease: ModelJob
) -> ModelJob:
    store = runner._runs

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
        binding = store.get_provider_binding(run.run_id)
        identity = f"{binding.provider}:{binding.model}"
        if not lease.quality_request or run.quality_provider != identity:
            return failed("quality_provider_unavailable")
        pack = resources(runner)
        if (
            run.status != RunStatus.TD_AWAITING_APPROVAL
            or not run.td_draft
            or make_task(run, "discover", pack).input_binding != lease.task.input_binding
        ):
            return failed("execution_input_stale")

        class JobModel:
            @property
            def identity(self) -> str:
                return identity

            def execute(self, task: ModelTaskInput) -> object:
                try:
                    if getattr(task.payload, "mode", None) == "repair":
                        target = getattr(task.payload, "target_issue_id", None)
                        if target and store.candidate_count(run.run_id, target) >= 3:
                            raise QualityProviderError("issue_budget_exhausted")
                        budget = store.model_budget(run.run_id)
                        if budget.candidates >= budget.policy.max_candidates:
                            raise QualityProviderError("run_candidate_budget_exhausted")
                    return invoke_job_model(store, lease, provider, task=task)
                except (ProviderError, ModelBudgetError) as error:
                    raise QualityProviderError(str(error)) from error
                except ValueError as error:
                    # Lease loss must not become a successful diagnostic commit.
                    if str(error) in ("job_model_budget_exhausted", "run_model_budget_exhausted"):
                        raise QualityProviderError(str(error)) from error
                    raise

        def candidate(issue_id: str, candidate_hash: str) -> None:
            with store._write_scope():
                store.require_lease(lease)
                try:
                    store.reserve_candidate(run.run_id, lease.command_id, issue_id, candidate_hash)
                except ModelBudgetError as error:
                    raise QualityProviderError(str(error)) from error

        staged = execute_cycle(
            run, lease.quality_request, JobModel(), pack, record_candidate=candidate
        )
        # Reproject through all deterministic guards; stale review stays stale.
        updated = runner._validated_update(
            run,
            {
                key: getattr(staged, key)
                for key in (
                    "td_draft",
                    "td_revisions",
                    "td_review",
                    "quality_issues",
                    "quality_patch_attempts",
                    "quality_executions",
                    "quality_audits",
                )
            },
        )
        return store.complete_job(lease, updated)
    except (ModelBoundaryError, ProviderError) as error:
        return failed(error.code)
    except ModelBudgetError as error:
        return failed(str(error))
    except ValueError as error:
        if str(error) in ("execution_lease_lost", "execution_input_stale"):
            return failed(str(error))
        return failed("quality_candidate_invalid")

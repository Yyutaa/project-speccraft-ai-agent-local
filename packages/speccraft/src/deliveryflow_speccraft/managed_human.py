"""Explicit human commands share persisted governance, never the model or Graph."""

from deliveryflow_contracts.execution import ManagedHumanRequest, RunSnapshot
from deliveryflow_contracts.prd import PrdRevisionRequest
from deliveryflow_contracts.quality import (
    QualityIssueDecisionRequest,
    QualityPatchRequest,
    QualityRiskAcceptanceRequest,
)
from deliveryflow_contracts.runs import AvailableCommand
from deliveryflow_contracts.td import RecordTdReviewRequest, TdApprovalRequest, TdRevisionRequest
from pydantic import BaseModel

from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    DuplicateCommand,
    GovernanceError,
    InvalidPrdRevision,
    InvalidRunTransition,
    PrdNotReady,
    RevisionConflict,
    RunRunner,
    TdObligationConflict,
)


def execute_human_command[T: BaseModel](
    runner: RunRunner, run_id: str, kind: AvailableCommand, command: ManagedHumanRequest[T]
) -> RunSnapshot:
    command = type(command).model_validate(command.model_dump())
    payload = command.request.model_dump(mode="json")
    expected = {
        "command_id": command.command_id,
        "actor_claim": command.actor_claim,
        "actor": command.actor_claim,
        "rationale": command.rationale,
    }
    if any(key in payload and payload[key] != value for key, value in expected.items()):
        raise GovernanceError("command_identity_conflict", 422)
    store = runner._runs
    try:
        with store._write_scope():
            if not runner.is_managed_run(run_id):
                raise GovernanceError("execution_mode_conflict", 409)
            store.accept_command(
                run_id,
                command.command_id,
                kind,
                command.model_dump(mode="json"),
                expected_version=command.expected_run_version,
                actor_claim=command.actor_claim,
                rationale=command.rationale,
            )
            if any(job.status in ("queued", "running") for job in store.jobs_for_run(run_id)):
                raise GovernanceError("run_execution_busy", 409)
            if kind is AvailableCommand.REVISE_PRD:
                runner.revise_prd(run_id, PrdRevisionRequest.model_validate(payload))
            elif kind is AvailableCommand.REVISE_TD:
                runner.revise_td(run_id, TdRevisionRequest.model_validate(payload))
            elif kind is AvailableCommand.RECORD_TD_REVIEW:
                runner.record_td_review(run_id, RecordTdReviewRequest.model_validate(payload))
            elif kind is AvailableCommand.DECIDE_TD_ISSUE:
                runner.decide_td_issue(run_id, QualityIssueDecisionRequest.model_validate(payload))
            elif kind is AvailableCommand.ACCEPT_TD_QUALITY_RISK:
                runner.accept_td_quality_risk(
                    run_id, QualityRiskAcceptanceRequest.model_validate(payload)
                )
            elif kind is AvailableCommand.PATCH_TD_ISSUE:
                runner.patch_td_issue(run_id, QualityPatchRequest.model_validate(payload))
            elif kind is AvailableCommand.APPROVE_TD:
                runner.approve_td(run_id, TdApprovalRequest.model_validate(payload))
            else:
                raise GovernanceError("unsupported_human_command", 422)
            if command.command_id not in store.commands[run_id]:
                store.commands[run_id].add(command.command_id)
            store.mark_command_committed(run_id, command.command_id)
            store.finish_command(run_id, command.command_id, "succeeded")
            return store.snapshot(run_id)
    except (
        InvalidRunTransition,
        RevisionConflict,
        ContentHashConflict,
        DuplicateCommand,
        PrdNotReady,
        InvalidPrdRevision,
        TdObligationConflict,
    ) as error:
        codes = {
            InvalidRunTransition: "invalid_run_transition",
            RevisionConflict: "revision_conflict",
            ContentHashConflict: "content_hash_conflict",
            DuplicateCommand: "duplicate_command",
            PrdNotReady: "prd_not_ready",
            InvalidPrdRevision: "invalid_prd_revision",
            TdObligationConflict: "td_obligation_conflict",
        }
        raise GovernanceError(codes[type(error)], 409) from error
    except ValueError as error:
        if str(error) in {"duplicate_command", "command_payload_conflict", "run_version_conflict"}:
            raise GovernanceError(str(error), 409) from error
        raise

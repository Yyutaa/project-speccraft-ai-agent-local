import pytest
from deliveryflow_contracts.execution import ManagedHumanRequest
from deliveryflow_contracts.prd import PrdRevisionRequest
from deliveryflow_contracts.runs import AvailableCommand
from deliveryflow_speccraft import managed
from deliveryflow_speccraft.managed_human import execute_human_command
from deliveryflow_speccraft.runner import GovernanceError
from test_managed_prd import author, ready, submission


def ready_prd(tmp_path):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="prd")
    return runner, runner.get_run(run.run_id)


def revision(runner, run):
    return ManagedHumanRequest[PrdRevisionRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id="human-revision",
        actor_claim="owner",
        rationale="clarify background",
        user_confirmed=True,
        request={
            "governance_contract_version": 2,
            "expected_revision": run.prd_draft.revision,
            "expected_content_hash": run.prd_draft.content_hash,
            "section_id": "background",
            "replacement_body": "Explicitly revised background.",
            "feedback": "clarify background",
        },
    )


def test_human_revision_is_atomic_and_receipted(tmp_path):
    runner, run = ready_prd(tmp_path)
    command = revision(runner, run)
    snapshot = execute_human_command(
        runner, run.run_id, AvailableCommand.REVISE_PRD, command
    )
    assert snapshot.run.prd_draft.revision == 2
    assert runner.get_command(run.run_id, command.command_id).domain_committed
    with pytest.raises(GovernanceError, match="duplicate_command"):
        execute_human_command(runner, run.run_id, AvailableCommand.REVISE_PRD, command)


def test_stale_hash_rolls_back_receipt_events_and_success_id(tmp_path):
    runner, run = ready_prd(tmp_path)
    command = revision(runner, run)
    command = command.model_copy(
        update={
            "request": command.request.model_copy(
                update={"expected_content_hash": "0" * 64}
            )
        }
    )
    before = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError, match="content_hash_conflict"):
        execute_human_command(runner, run.run_id, AvailableCommand.REVISE_PRD, command)
    assert runner.get_snapshot(run.run_id) == before
    with pytest.raises(KeyError):
        runner.get_command(run.run_id, command.command_id)


def test_active_job_refuses_human_command_without_receipt(tmp_path):
    from test_managed_td import approved

    runner, _, _, accepted = approved(tmp_path)
    run = runner.get_run(accepted.run_id)
    command = revision(runner, run)
    before = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError, match="run_execution_busy"):
        execute_human_command(runner, run.run_id, AvailableCommand.REVISE_PRD, command)
    assert runner.get_snapshot(run.run_id) == before


def test_actor_mismatch_rejected_before_persistence(tmp_path):
    from deliveryflow_contracts.td import TdApprovalRequest
    from test_managed_td import approved, td_provider
    from test_td_review import approval

    runner, _, _, accepted = approved(tmp_path)
    managed.execute_model_job(runner, td_provider(), owner="td")
    run = runner.get_run(accepted.run_id)
    command = ManagedHumanRequest[TdApprovalRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id="approve-td",
        actor_claim="different",
        rationale="审阅后批准",
        user_confirmed=True,
        request=approval(run),
    )
    with pytest.raises(GovernanceError, match="command_identity_conflict"):
        execute_human_command(runner, run.run_id, AvailableCommand.APPROVE_TD, command)


def test_human_review_then_explicit_approval_publishes_three_artifacts(tmp_path):
    from deliveryflow_contracts.td import RecordTdReviewRequest, TdApprovalRequest
    from deliveryflow_speccraft import managed_quality
    from governance_helpers import td_review_request
    from test_managed_quality import command as quality_command
    from test_managed_quality import provider, ready_quality
    from test_td_review import approval

    runner, run = ready_quality(tmp_path)
    managed_quality.submit_quality(runner, run.run_id, quality_command(runner, run))
    managed_quality.execute_quality_job(
        runner, provider(), runner._runs.claim_next("quality")
    )
    run = runner.get_run(run.run_id)
    assert run.quality_audit_current
    request = td_review_request(run)
    command = ManagedHumanRequest[RecordTdReviewRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id=request.command_id,
        actor_claim=request.actor_claim,
        rationale=request.rationale,
        user_confirmed=True,
        request=request,
    )
    reviewed = execute_human_command(
        runner, run.run_id, AvailableCommand.RECORD_TD_REVIEW, command
    ).run
    request = approval(reviewed)
    command = ManagedHumanRequest[TdApprovalRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id="final-approval",
        actor_claim=request.actor,
        rationale=request.rationale,
        user_confirmed=True,
        request=request,
    )
    published = execute_human_command(
        runner, run.run_id, AvailableCommand.APPROVE_TD, command
    ).run
    assert published.status == "completed"
    assert (
        published.delivery_spec is not None and len(published.artifact_envelopes) == 3
    )


def test_human_model_false_positive_decision_needs_no_online_quality_model(tmp_path):
    from deliveryflow_contracts.quality import QualityIssueDecisionRequest
    from deliveryflow_speccraft import managed_quality
    from test_managed_quality import command as quality_command
    from test_managed_quality import provider, ready_quality
    from test_quality_cycle import ScriptedModel, request

    runner, run = ready_quality(tmp_path)
    managed_quality.submit_quality(runner, run.run_id, quality_command(runner, run))
    managed_quality.execute_quality_job(
        runner,
        provider(ScriptedModel(bad_patch=True)),
        runner._runs.claim_next("quality"),
    )
    run = runner.get_run(run.run_id)
    decision = QualityIssueDecisionRequest(
        **request(run, "dismiss").model_dump(),
        issue_id=run.quality_issues[0].issue_id,
        rationale="human verified false positive",
        user_confirmed=True,
    )
    runner._quality_model = None
    command = ManagedHumanRequest[QualityIssueDecisionRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id=decision.command_id,
        actor_claim=decision.actor_claim,
        rationale=decision.rationale,
        user_confirmed=True,
        request=decision,
    )
    result = execute_human_command(
        runner, run.run_id, AvailableCommand.DECIDE_TD_ISSUE, command
    )
    assert result.run.quality_issues[0].status == "resolved"

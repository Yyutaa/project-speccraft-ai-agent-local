"""Read projections distinguish domain capability from currently executable commands."""

from deliveryflow_speccraft.managed_quality import submit_quality
from deliveryflow_speccraft.workbench import read_workbench
from test_managed_prd import ready, submission
from test_managed_prd_controls import control
from test_managed_quality import command, ready_quality
from test_managed_td import approved


def test_queued_task_closes_domain_actions_and_exposes_only_job_cancel(tmp_path):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    projection = read_workbench(runner, run.run_id)
    assert projection.execution_mode == "managed"
    assert projection.available_commands == ()
    assert projection.jobs[-1].job_id == accepted.job_id
    assert projection.jobs[-1].available_commands == ("cancel_execution",)
    assert projection.command_receipts[-1].domain_committed
    assert projection.event_cursor > 0


def test_active_quality_job_masks_stale_domain_approval_controls(tmp_path):
    runner, run = ready_quality(tmp_path)
    accepted = submit_quality(runner, run.run_id, command(runner, run))
    original = runner.get_run(run.run_id)
    assert "revise_td" in original.available_commands
    projection = read_workbench(runner, run.run_id)
    assert not projection.available_commands
    assert projection.run == original  # Read model must not rewrite authority.
    assert projection.jobs[-1].job_id == accepted.job_id


def test_exhausted_run_budget_removes_only_model_execution_not_human_revision(tmp_path):
    runner, run = ready_quality(tmp_path)
    runner._runs._connection.execute(
        "UPDATE model_budgets SET calls=32,candidates=8 WHERE run_id=?", (run.run_id,)
    )
    projection = read_workbench(runner, run.run_id)
    assert "run_td_quality" not in projection.available_commands
    assert "patch_td_issue" not in projection.available_commands
    assert "revise_td" in projection.available_commands
    assert "record_td_review" in projection.available_commands


def test_cancelled_task_projection_uses_fresh_version_and_bound_retry(tmp_path):
    runner, service, _, accepted = approved(tmp_path)
    service.cancel_job(
        accepted.run_id, accepted.job_id, control(runner, accepted.run_id)
    )
    projection = read_workbench(runner, accepted.run_id)
    assert projection.jobs[-1].available_commands == ("retry_execution",)
    assert projection.jobs[-1].run_version == projection.run_version


def test_managed_issue_patch_is_a_versioned_human_command(tmp_path, monkeypatch):
    from deliveryflow_contracts.execution import ManagedHumanRequest
    from deliveryflow_contracts.quality import QualityPatchRequest
    from test_managed_prd_api import client_for
    from test_provider_adapter import config
    from test_quality_cycle import ScriptedModel, subject
    from test_td_quality import patch_request, quality_run

    runner = subject(ScriptedModel(), tmp_path / "patch.sqlite3")
    run = quality_run(runner)
    runner._runs.bind_provider(run.run_id, config().binding)
    request = patch_request(run, body="补齐前端说明。")
    wrapper = ManagedHumanRequest[QualityPatchRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id=request.command_id,
        actor_claim=request.actor_claim,
        rationale="修复明确占位问题",
        user_confirmed=True,
        request=request,
    )
    client = client_for(runner, monkeypatch)
    response = client.post(
        f"/api/managed/runs/{run.run_id}/td/issues/patch",
        json=wrapper.model_dump(mode="json"),
    )
    assert response.status_code == 200
    current = runner.get_run(run.run_id)
    assert current.td_draft.revision == run.td_draft.revision + 1
    assert current.prd_draft == run.prd_draft and current.td_review.status == "stale"
    assert runner.get_command(run.run_id, request.command_id).domain_committed

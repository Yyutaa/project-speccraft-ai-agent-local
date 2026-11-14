"""The full managed chain ends only after current human review and explicit approval."""

import sqlite3

import pytest
from deliveryflow_contracts.execution import ManagedHumanRequest
from deliveryflow_contracts.td import RecordTdReviewRequest, TdApprovalRequest
from deliveryflow_speccraft import managed
from governance_helpers import td_review_request
from test_managed_prd_api import client_for
from test_managed_quality import command, provider
from test_managed_td import approved, td_provider
from test_td_review import approval


def review_body(runner, run):
    request = td_review_request(run)
    return ManagedHumanRequest[RecordTdReviewRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id=request.command_id,
        actor_claim=request.actor_claim,
        rationale=request.rationale,
        user_confirmed=True,
        request=request,
    ).model_dump(mode="json")


def approval_body(runner, run):
    request = approval(run)
    return ManagedHumanRequest[TdApprovalRequest](
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id="delivery-approval",
        actor_claim=request.actor,
        rationale=request.rationale,
        user_confirmed=True,
        request=request,
    ).model_dump(mode="json")


def current_review(tmp_path, monkeypatch):
    runner, _, _, accepted = approved(
        tmp_path
    )  # Real service: create -> clarify -> PRD -> approve.
    client = client_for(runner, monkeypatch)
    assert (
        managed.execute_model_job(runner, td_provider(), owner="td").status
        == "succeeded"
    )
    run = runner.get_run(accepted.run_id)
    response = client.post(
        f"/api/managed/runs/{run.run_id}/td/quality/run",
        json=command(runner, run).model_dump(mode="json"),
    )
    assert response.status_code == 202
    assert (
        managed.execute_model_job(runner, provider(), owner="quality").status
        == "succeeded"
    )
    run = runner.get_run(run.run_id)
    assert run.td_review.status == "stale" and run.quality_audit_current
    # A machine audit cannot replace independent human review.
    blocked = client.post(
        f"/api/managed/runs/{run.run_id}/td/approve", json=approval_body(runner, run)
    )
    assert blocked.status_code == 409
    assert runner.get_run(run.run_id).td_approval is None
    response = client.post(
        f"/api/managed/runs/{run.run_id}/td/reviews", json=review_body(runner, run)
    )
    assert response.status_code == 200
    return runner, client, runner.get_run(run.run_id)


def test_managed_full_chain_publishes_matching_approved_artifacts(
    tmp_path, monkeypatch
):
    runner, client, run = current_review(tmp_path, monkeypatch)
    response = client.post(
        f"/api/managed/runs/{run.run_id}/td/approve", json=approval_body(runner, run)
    )
    assert response.status_code == 200
    done = runner.get_run(run.run_id)
    assert done.status == "completed"
    assert done.delivery_spec.prd.content_hash == done.prd_approval.content_hash
    assert done.delivery_spec.td.content_hash == done.td_approval.content_hash
    assert len(done.artifact_envelopes) == 3
    assert (
        runner.get_model_budget(run.run_id).model_calls == 7
    )  # clarification/PRD/TD + 4 quality


def test_final_event_failure_rolls_back_approval_artifacts_and_receipt(
    tmp_path, monkeypatch
):
    runner, client, run = current_review(tmp_path, monkeypatch)
    before = runner.get_snapshot(run.run_id)
    store = runner._runs
    store._connection.execute(
        "CREATE TRIGGER fail_publish BEFORE INSERT ON run_events WHEN NEW.event_type='command.committed' BEGIN SELECT RAISE(ABORT,'publish interrupted'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="publish interrupted"):
        client.post(
            f"/api/managed/runs/{run.run_id}/td/approve",
            json=approval_body(runner, run),
        )
    assert runner.get_snapshot(run.run_id) == before
    assert run.td_approval is None and run.artifact_envelopes == ()
    with pytest.raises(KeyError):
        runner.get_command(run.run_id, "delivery-approval")

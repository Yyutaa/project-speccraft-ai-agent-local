"""REST accepts explicit user decisions; Worker owns all PRD model execution."""

from deliveryflow_speccraft import managed
from deliveryflow_speccraft.workflow import RunWorkflow
from fastapi.testclient import TestClient
from governance_helpers import clarification_body
from test_managed_prd import author, ready
from test_managed_prd_controls import control

from apps.api import main as api


def client_for(runner, monkeypatch):
    monkeypatch.setattr(api, "runner", runner)
    monkeypatch.setattr(api, "workflow", RunWorkflow(runner))
    return TestClient(api.app)


def body(runner, run):
    return {
        "execution_contract_version": 1,
        "expected_run_version": runner.get_snapshot(run.run_id).run_version,
        "request": clarification_body(run, "api-prd-command"),
    }


def test_clarification_returns_committed_202_without_model_and_worker_delivers_prd(
    tmp_path, monkeypatch
):
    runner, _, run = ready(tmp_path)
    client = client_for(runner, monkeypatch)
    response = client.post(
        f"/api/managed/runs/{run.run_id}/clarifications", json=body(runner, run)
    )
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["receipt"]["status"] == "accepted"
    assert accepted["receipt"]["domain_committed"] is True
    assert (
        client.get(f"/api/runs/{run.run_id}/snapshot").json()["run"]["status"]
        == "prd_preparing"
    )
    assert runner.get_model_budget(run.run_id).model_calls == 1
    managed.execute_model_job(runner, author(), owner="api-worker")
    current = client.get(f"/api/runs/{run.run_id}/snapshot").json()["run"]
    assert (
        current["status"] == "prd_awaiting_approval" and current["prd_approval"] is None
    )
    assert runner.get_model_budget(run.run_id).model_calls == 2


def test_stale_version_duplicate_payload_and_invalid_confirmation_are_refused_without_changes(
    tmp_path, monkeypatch
):
    runner, _, run = ready(tmp_path)
    client = client_for(runner, monkeypatch)
    payload = body(runner, run)
    baseline = runner.get_snapshot(run.run_id)
    route = f"/api/managed/runs/{run.run_id}/clarifications"
    stale = client.post(route, json={**payload, "expected_run_version": 0})
    assert (
        stale.status_code == 409
        and stale.json()["detail"]["code"] == "run_version_conflict"
    )
    invalid = client.post(
        route,
        json={**payload, "request": {**payload["request"], "user_confirmed": False}},
    )
    assert invalid.status_code == 422
    assert runner.get_snapshot(run.run_id) == baseline
    assert client.post(route, json=payload).status_code == 202
    repeated = client.post(route, json=payload)
    assert (
        repeated.status_code == 409
        and repeated.json()["detail"]["code"] == "duplicate_command"
    )
    conflict = client.post(
        route,
        json={**payload, "request": {**payload["request"], "rationale": "changed"}},
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["detail"]["code"] == "command_payload_conflict"
    )


def test_cancel_and_retry_are_explicit_versioned_commands_and_job_projection_supplies_actions(
    tmp_path, monkeypatch
):
    runner, _, run = ready(tmp_path)
    client = client_for(runner, monkeypatch)
    accepted = client.post(
        f"/api/managed/runs/{run.run_id}/clarifications", json=body(runner, run)
    ).json()
    job_route = f"/api/runs/{run.run_id}/jobs/{accepted['job_id']}"
    control_route = f"/api/managed/runs/{run.run_id}/jobs/{accepted['job_id']}"
    projection = client.get(job_route).json()
    assert projection["available_commands"] == ["cancel_execution"]
    cancel = client.post(
        control_route + "/cancel",
        json=control(runner, run.run_id).model_dump(mode="json"),
    )
    assert (
        cancel.status_code == 200
        and cancel.json()["receipt"]["domain_committed"] is True
    )
    assert client.get(job_route).json()["available_commands"] == ["retry_execution"]
    retried = client.post(
        control_route + "/retry",
        json=control(runner, run.run_id, "retry-1").model_dump(mode="json"),
    )
    assert retried.status_code == 202 and retried.json()["job_id"] != accepted["job_id"]
    assert client.get(job_route).json()["available_commands"] == []
    managed.execute_model_job(runner, author(), owner="api-worker")
    assert runner.get_run(run.run_id).prd_draft is not None


def test_unknown_run_and_cross_run_job_are_404(tmp_path, monkeypatch):
    runner, service, run = ready(tmp_path)
    client = client_for(runner, monkeypatch)
    payload = body(runner, run)
    assert (
        client.post(
            "/api/managed/runs/missing/clarifications", json=payload
        ).status_code
        == 404
    )
    from test_managed_clarification import request

    other = service.create_run(request())
    command = control(runner, other.run_id)
    target = runner._runs.jobs_for_run(run.run_id)[0]
    for operation in ("cancel", "retry"):
        response = client.post(
            f"/api/managed/runs/{other.run_id}/jobs/{target.job_id}/{operation}",
            json=command.model_dump(mode="json"),
        )
        assert response.status_code == 404

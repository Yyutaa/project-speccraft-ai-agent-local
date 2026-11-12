"""The new API accepts background work without executing the model."""

from fastapi.testclient import TestClient
from test_managed_clarification import http_model, setup

from apps.api import main as api


def configure(monkeypatch):
    monkeypatch.setenv("SPECCRAFT_PROVIDER", "deepseek")
    monkeypatch.setenv("SPECCRAFT_MODEL", "configured-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret-never-disclose")


def test_background_creation_is_202_and_existing_reads_do_not_execute_models(
    tmp_path, monkeypatch
):
    configure(monkeypatch)
    runner, _ = setup(tmp_path)
    monkeypatch.setattr(api, "runner", runner)
    from deliveryflow_speccraft.workflow import RunWorkflow

    monkeypatch.setattr(api, "workflow", RunWorkflow(runner))
    client = TestClient(api.app)
    response = client.post(
        "/api/managed/runs",
        json={
            "execution_contract_version": 1,
            "request": {
                "governance_contract_version": 2,
                "requirement": "创建导出工具。",
            },
        },
    )
    assert response.status_code == 202
    accepted = response.json()
    run_id = accepted["run_id"]
    assert accepted["receipt"]["status"] == "accepted"
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "context_preparing"
    assert (
        client.get(f"/api/runs/{run_id}/snapshot").json()["model_budget"]["model_calls"]
        == 0
    )
    job = client.get(f"/api/runs/{run_id}/jobs/{accepted['job_id']}")
    assert job.status_code == 200 and job.json()["status"] == "queued"
    assert "task" not in job.json() and "test-secret" not in job.text
    from deliveryflow_speccraft.managed import execute_clarification_job

    execute_clarification_job(runner, http_model(), owner="test-worker")
    assert (
        client.get(f"/api/runs/{run_id}").json()["status"] == "awaiting_clarification"
    )
    receipt = client.get(f"/api/runs/{run_id}/commands/{accepted['command_id']}").json()
    assert receipt["status"] == "succeeded"
    blocked = client.post(
        f"/api/runs/{run_id}/approvals/prd",
        json={
            "governance_contract_version": 2,
            "revision": 1,
            "content_hash": "0" * 64,
            "actor": "reviewer",
            "rationale": "explicit approval request",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "execution_mode_conflict"


def test_missing_provider_configuration_rejects_without_persisting_or_faking(
    tmp_path, monkeypatch
):
    configure(monkeypatch)
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    runner, _ = setup(tmp_path)
    monkeypatch.setattr(api, "runner", runner)
    response = TestClient(api.app).post(
        "/api/managed/runs",
        json={
            "execution_contract_version": 1,
            "request": {
                "governance_contract_version": 2,
                "requirement": "创建导出工具。",
            },
        },
    )
    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.text and "test-secret" not in response.text
    assert runner.list_run_ids() == ()


def test_execution_contract_is_explicit_and_job_reads_are_run_scoped(
    tmp_path, monkeypatch
):
    configure(monkeypatch)
    runner, service = setup(tmp_path)
    monkeypatch.setattr(api, "runner", runner)
    client = TestClient(api.app)
    assert (
        client.post(
            "/api/managed/runs",
            json={
                "request": {
                    "governance_contract_version": 2,
                    "requirement": "创建导出工具。",
                },
            },
        ).status_code
        == 422
    )
    from test_managed_clarification import request

    first, second = service.create_run(request()), service.create_run(request())
    assert (
        client.get(f"/api/runs/{second.run_id}/jobs/{first.job_id}").status_code == 404
    )

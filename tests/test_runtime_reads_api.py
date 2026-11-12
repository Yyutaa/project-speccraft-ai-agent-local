"""REST reads expose persisted versions and accounting without driving a Graph."""

import pytest
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft.composition import build_runner
from fastapi.testclient import TestClient
from test_composition import ROOT

from apps.api import main


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    runner = build_runner(ROOT, database_path=tmp_path / "runs.db")
    monkeypatch.setattr(main, "runner", runner)
    run = runner.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="不得随事件暴露。",
        )
    )
    return runner, run, TestClient(main.app)


def test_snapshot_and_events_do_not_advance_workflow(runtime, monkeypatch):
    runner, run, client = runtime

    def never(*args):
        raise AssertionError("a snapshot read must not execute the Graph")

    monkeypatch.setattr(main.workflow, "get_run", never)
    result = client.get(f"/api/runs/{run.run_id}/snapshot")
    assert result.status_code == 200
    assert result.json()["run"] == run.model_dump(mode="json")
    assert result.json()["run_version"] == 1
    events = client.get(f"/api/runs/{run.run_id}/events?after=0")
    assert events.status_code == 200
    assert events.json()[0]["event_type"] == "run.changed"
    assert run.requirement not in events.text
    assert runner.get_run(run.run_id) == run


def test_budget_is_read_only_and_unknown_run_or_invalid_cursor_are_rejected(runtime):
    runner, run, client = runtime
    response = client.get(f"/api/runs/{run.run_id}/model-budget")
    assert response.status_code == 200
    assert response.json()["model_calls"] == 0
    assert response.json()["policy"]["max_model_calls"] == 32
    assert client.get("/api/runs/unknown/snapshot").status_code == 404
    assert client.get("/api/runs/unknown/events").status_code == 404
    assert client.get("/api/runs/unknown/model-budget").status_code == 404
    assert client.get(f"/api/runs/{run.run_id}/events?after=-1").status_code == 422
    assert (
        client.post(
            f"/api/runs/{run.run_id}/model-budget",
            json={
                "max_model_calls": 1000,
            },
        ).status_code
        == 405
    )
    assert runner.get_model_budget(run.run_id).policy.max_model_calls == 32


def test_command_receipt_read_does_not_claim_the_command_was_executed(runtime):
    from deliveryflow_contracts.runs import AvailableCommand

    runner, run, client = runtime
    receipt = runner._runs.accept_command(
        run.run_id,
        "accepted-only",
        AvailableCommand.RUN_TD_QUALITY,
        {},
        expected_version=1,
    )
    response = client.get(f"/api/runs/{run.run_id}/commands/accepted-only")
    assert response.status_code == 200
    assert response.json() == receipt.model_dump(mode="json")
    assert response.json()["status"] == "accepted"
    assert runner.get_run(run.run_id) == run
    assert client.get(f"/api/runs/{run.run_id}/commands/unknown").status_code == 404

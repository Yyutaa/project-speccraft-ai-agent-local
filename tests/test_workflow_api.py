from fastapi.testclient import TestClient

from apps.api import main as api_main


def test_api_creates_run_with_real_interrupt() -> None:
    client = TestClient(api_main.app)
    response = client.post("/api/runs", json={"requirement": "创建导出工具。"})

    assert response.status_code == 201
    run = response.json()
    assert api_main.workflow.pending_gate(run["run_id"]) == "await_clarification"


def test_api_reports_committed_domain_state_if_checkpoint_update_fails(monkeypatch) -> None:
    client = TestClient(api_main.app)
    created = client.post("/api/runs", json={"requirement": "创建导出工具。"}).json()
    batch = created["clarification_batch"]
    original = api_main.workflow._graph.invoke
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("checkpoint unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(api_main.workflow._graph, "invoke", fail_once)
    response = client.post(
        f"/api/runs/{created['run_id']}/clarifications/answers",
        json={
            "expected_revision": created["ledger"]["revision"],
            "command_id": "sync-failure-command",
            "answers": [
                {
                    "question_id": item["question_id"],
                    "selected_option_id": item["options"][0]["option_id"],
                }
                for item in batch["proposals"]
                if item["gap_id"] in batch["blocking_gap_ids"]
            ],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "workflow_sync_pending",
        "run_id": created["run_id"],
        "committed": True,
    }
    read = client.get(f"/api/runs/{created['run_id']}")
    assert read.status_code == 200
    assert read.json()["status"] == "prd_awaiting_approval"
    assert api_main.workflow.pending_gate(created["run_id"]) == "await_prd_review"


def test_api_reports_uncommitted_checkpoint_failure_before_domain_command(monkeypatch) -> None:
    client = TestClient(api_main.app)
    created = client.post("/api/runs", json={"requirement": "创建导出工具。"}).json()
    batch = created["clarification_batch"]

    def unavailable(*args, **kwargs):
        raise RuntimeError("checkpoint read unavailable")

    with monkeypatch.context() as context:
        context.setattr(api_main.workflow._graph, "get_state", unavailable)
        response = client.post(
            f"/api/runs/{created['run_id']}/clarifications/answers",
            json={
                "expected_revision": created["ledger"]["revision"],
                "command_id": "preflight-failure-command",
                "answers": [
                    {
                        "question_id": item["question_id"],
                        "selected_option_id": item["options"][0]["option_id"],
                    }
                    for item in batch["proposals"]
                    if item["gap_id"] in batch["blocking_gap_ids"]
                ],
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "workflow_out_of_sync", "committed": False,
    }
    assert client.get(f"/api/runs/{created['run_id']}").json() == created

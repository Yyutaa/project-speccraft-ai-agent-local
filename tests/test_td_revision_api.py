import pytest
from fastapi.testclient import TestClient
from governance_helpers import td_review_body
from test_td_review_api import td_run

from apps.api import main as api_main

client = TestClient(api_main.app)


def body(run, **changes):
    return {
        "governance_contract_version": 2,
        "command_id": "revise-http",
        "section_id": "frontend",
        "replacement_body": "前端依据冻结权限显示操作。",
        "feedback": "补充前端说明",
        "actor_claim": "tech-owner",
        "expected_td_revision": run["td_draft"]["revision"],
        "expected_td_content_hash": run["td_draft"]["content_hash"],
        "expected_review_revision": run["td_review"]["review_revision"],
        **changes,
    }


def test_revision_http_reinterrupts_same_gate_and_retains_history():
    run = td_run()
    key = api_main.workflow.gate_key(run["run_id"])
    response = client.post(f"/api/runs/{run['run_id']}/td/revisions", json=body(run))
    assert response.status_code == 200
    revised = response.json()
    assert revised["td_draft"]["revision"] == 2
    assert revised["td_readiness"]["ready"] is True
    assert revised["td_review"]["status"] == "stale"
    assert len(revised["td_revisions"]) == 2
    assert api_main.workflow.pending_gate(run["run_id"]) == "await_td_review"
    assert api_main.workflow.gate_key(run["run_id"]) != key
    duplicate = client.post(
        f"/api/runs/{run['run_id']}/td/revisions", json=body(revised)
    )
    assert (
        duplicate.status_code == 409
        and duplicate.json()["detail"]["code"] == "duplicate_command"
    )
    assert client.get(f"/api/runs/{run['run_id']}").json() == revised


@pytest.mark.parametrize(
    "change,status,code",
    [
        ({"expected_td_revision": 99}, 409, "revision_conflict"),
        ({"expected_td_content_hash": "0" * 64}, 409, "content_hash_conflict"),
        ({"expected_review_revision": 99}, 409, "td_review_conflict"),
        ({"section_id": "invented"}, 422, "invalid_td_revision"),
        ({"replacement_body": "## unexpected"}, 422, "invalid_td_revision"),
        ({"replacement_body": "  "}, 422, "invalid_td_revision"),
        ({"expected_td_revision": True}, 422, "invalid_td_revision"),
    ],
)
def test_invalid_revision_http_is_atomic_and_uses_stable_error_codes(
    change, status, code
):
    run = td_run()
    url = f"/api/runs/{run['run_id']}/td/revisions"
    response = client.post(url, json=body(run, **change))
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert client.get(f"/api/runs/{run['run_id']}").json() == run
    assert client.post(url, json=body(run)).status_code == 200


@pytest.mark.parametrize("endpoint", ["revisions", "reviews"])
def test_td_command_commit_then_sync_failure_recovers_once_by_read(
    endpoint, monkeypatch
):
    run = td_run()
    original = api_main.workflow._graph.invoke
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("checkpoint unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(api_main.workflow._graph, "invoke", fail_once)
    request = body(run) if endpoint == "revisions" else td_review_body(run)
    response = client.post(f"/api/runs/{run['run_id']}/td/{endpoint}", json=request)
    assert response.status_code == 503
    assert response.json()["detail"]["committed"] is True
    assert response.json()["detail"]["code"] == "workflow_sync_pending"
    updated = client.get(f"/api/runs/{run['run_id']}").json()
    assert updated["td_review"]["review_revision"] == 1
    assert len(updated["td_revisions"]) == (2 if endpoint == "revisions" else 1)
    assert len(updated["td_review_records"]) == (0 if endpoint == "revisions" else 1)
    assert api_main.workflow.pending_gate(run["run_id"]) == "await_td_review"
    assert api_main.workflow.gate_key(run["run_id"]) == api_main.workflow.gate_key_for(
        api_main.runner.get_run(run["run_id"])
    )
    assert client.get(f"/api/runs/{run['run_id']}").json() == updated


@pytest.mark.parametrize("endpoint", ["revisions", "reviews"])
def test_td_command_missing_checkpoint_is_closed_without_domain_write(endpoint):
    run = td_run()
    api_main.workflow._checkpointer.delete_thread(run["run_id"])
    request = body(run) if endpoint == "revisions" else td_review_body(run)
    response = client.post(f"/api/runs/{run['run_id']}/td/{endpoint}", json=request)
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "workflow_out_of_sync",
        "committed": False,
    }
    assert api_main.runner.get_run(run["run_id"]).model_dump(mode="json") == run


def test_parent_run_http_records_trace_and_rejects_missing_parent():
    parent = td_run()
    response = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "重新提供需求",
            "parent_run_id": parent["run_id"],
        },
    )
    assert response.status_code == 201
    child = response.json()
    assert child["parent_run_id"] == parent["run_id"] and child["ledger"]["facts"] == []
    assert child["prd_approval"] is None and child["td_review"] is None
    assert client.get(f"/api/runs/{parent['run_id']}").json() == parent
    response = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "新的需求",
            "parent_run_id": "lost-after-restart",
        },
    )
    assert (
        response.status_code == 404
        and response.json()["detail"]["code"] == "run_not_found"
    )

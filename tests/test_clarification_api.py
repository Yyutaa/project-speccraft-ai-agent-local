from fastapi.testclient import TestClient
from governance_helpers import clarification_body

from apps.api.main import app

client = TestClient(app)


def test_clarification_post_preflight_is_allowed_from_web_origin() -> None:
    response = client.options(
        "/api/runs/run-id/clarifications/answers",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


def create_waiting_run() -> tuple[dict, dict]:
    response = client.post(
        "/api/runs",
        json={"governance_contract_version": 2, "requirement": "创建一个导出工具。"},
    )
    assert response.status_code == 201
    run = response.json()
    assert run["clarification_batch"] is not None
    request = clarification_body(run, "clarification-command")
    return run, request


def test_api_waits_for_explicit_answers_before_creating_prd() -> None:
    waiting, request = create_waiting_run()

    assert waiting["status"] == "awaiting_clarification"
    assert waiting["prd_draft"] is None
    assert len(waiting["clarification_batch"]["blocking_gap_ids"]) == 5

    response = client.post(f"/api/runs/{waiting['run_id']}/clarifications/answers", json=request)
    resumed = response.json()

    assert response.status_code == 200
    assert resumed["status"] == "prd_awaiting_approval"
    assert resumed["prd_draft"] is not None
    assert len([fact for fact in resumed["ledger"]["facts"] if fact["kind"] == "decision"]) == 5


def test_partial_answers_are_rejected_without_advancing_run() -> None:
    waiting, request = create_waiting_run()
    request["answers"] = request["answers"][:1]

    response = client.post(f"/api/runs/{waiting['run_id']}/clarifications/answers", json=request)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_clarification"
    assert client.get(f"/api/runs/{waiting['run_id']}").json() == waiting


def test_stale_revision_and_duplicate_command_are_rejected() -> None:
    waiting, request = create_waiting_run()
    stale = {**request, "expected_revision": request["expected_revision"] + 1}

    stale_response = client.post(
        f"/api/runs/{waiting['run_id']}/clarifications/answers", json=stale
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["detail"]["code"] == "revision_conflict"
    assert client.get(f"/api/runs/{waiting['run_id']}").json() == waiting

    accepted = client.post(f"/api/runs/{waiting['run_id']}/clarifications/answers", json=request)
    repeated = client.post(f"/api/runs/{waiting['run_id']}/clarifications/answers", json=request)

    assert accepted.status_code == 200
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "duplicate_command"
    assert client.get(f"/api/runs/{waiting['run_id']}").json() == accepted.json()


def test_prd_cannot_be_approved_while_clarification_is_pending() -> None:
    waiting, _ = create_waiting_run()

    response = client.post(
        f"/api/runs/{waiting['run_id']}/approvals/prd",
        json={
            "governance_contract_version": 2,
            "revision": 1,
            "content_hash": "0" * 64,
            "actor": "tester",
            "rationale": "attempt",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_run_transition"
    assert client.get(f"/api/runs/{waiting['run_id']}").json() == waiting

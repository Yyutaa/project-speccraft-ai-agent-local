import pytest
from fastapi.testclient import TestClient
from governance_helpers import td_review_body
from test_run_api import create_prd_ready_run, prd_approval_body, td_approval_body

from apps.api import main as api_main

client = TestClient(api_main.app)


def td_run():
    prd = create_prd_ready_run("人工审阅测试")
    response = client.post(
        f"/api/runs/{prd['run_id']}/approvals/prd", json=prd_approval_body(prd)
    )
    assert response.status_code == 200
    return response.json()


def test_public_review_endpoint_reinterrupts_gate_and_allows_bound_approval():
    run = td_run()
    key = api_main.workflow.gate_key(run["run_id"])
    reviewed = client.post(
        f"/api/runs/{run['run_id']}/td/reviews", json=td_review_body(run)
    )
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["td_review"]["status"] == "ready"
    assert body["td_review_records"][-1]["human_conclusion"] == "no_conflict_observed"
    assert api_main.workflow.gate_key(run["run_id"]) != key
    assert api_main.workflow.pending_gate(run["run_id"]) == "await_td_review"
    done = client.post(
        f"/api/runs/{run['run_id']}/approvals/td", json=td_approval_body(body)
    )
    assert done.status_code == 200
    assert (
        done.json()["td_approval"]["review_id"]
        == body["td_review"]["current_review_id"]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"producer_kind": "model"},
        {"computed_status": "ready"},
        {"user_confirmed": False},
        {"human_conclusion": "fixed"},
        {"findings": [{"disposition": "fixed"}]},
    ],
)
def test_model_producer_or_client_ready_or_invalid_judgment_is_rejected(change):
    run = td_run()
    response = client.post(
        f"/api/runs/{run['run_id']}/td/reviews", json=td_review_body(run, **change)
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_td_review"
    assert client.get(f"/api/runs/{run['run_id']}").json() == run


def test_review_invalid_binding_and_stale_review_approval_have_domain_codes():
    run = td_run()
    url = f"/api/runs/{run['run_id']}/td/reviews"
    bad = td_review_body(run)
    bad["binding"]["td_content_hash"] = "0" * 64
    response = client.post(url, json=bad)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "td_review_conflict"
    reviewed = client.post(url, json=td_review_body(run)).json()
    second = client.post(url, json=td_review_body(reviewed, "review-2")).json()
    response = client.post(
        f"/api/runs/{run['run_id']}/approvals/td", json=td_approval_body(reviewed)
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "td_review_conflict"
    assert client.get(f"/api/runs/{run['run_id']}").json() == second


def test_valid_finding_is_saved_as_blocked_and_empty_history_reset_is_rejected():
    run = td_run()
    url = f"/api/runs/{run['run_id']}/td/reviews"
    item = {
        "finding_id": "conflict-1",
        "producer_kind": "human",
        "category": "product_conflict",
        "obligation_ids": [run["td_draft"]["obligations"][0]["obligation_id"]],
        "prd_excerpt": {
            "start": 0,
            "end": 10,
            "excerpt": run["prd_draft"]["content"][:10],
        },
        "td_excerpt": {
            "start": 0,
            "end": 10,
            "excerpt": run["td_draft"]["content"][:10],
        },
        "reason": "需确认正文承诺",
        "disposition": "open",
    }
    response = client.post(
        url,
        json=td_review_body(run, findings=[item], human_conclusion="changes_required"),
    )
    assert response.status_code == 200
    blocked = response.json()
    assert blocked["td_review"]["status"] == "blocked"
    approval = client.post(
        f"/api/runs/{run['run_id']}/approvals/td", json=td_approval_body(blocked)
    )
    assert approval.status_code == 409
    assert approval.json()["detail"]["code"] == "td_review_blocked"
    empty = client.post(url, json=td_review_body(blocked, "review-2"))
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "invalid_td_review"
    assert client.get(f"/api/runs/{run['run_id']}").json() == blocked
    duplicate = client.post(url, json=td_review_body(blocked))
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_command"


def test_missing_human_review_is_a_domain_409_and_rechecks_cannot_fix_same_body():
    run = td_run()
    response = client.post(
        f"/api/runs/{run['run_id']}/approvals/td", json=td_approval_body(run)
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "td_review_required"
    response = client.post(
        f"/api/runs/{run['run_id']}/td/reviews",
        json=td_review_body(
            run,
            rechecks=[
                {
                    "finding_id": "invented",
                    "outcome": "fixed",
                    "rationale": "同正文不能标记已修复",
                }
            ],
        ),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_td_review"
    assert client.get(f"/api/runs/{run['run_id']}").json() == run


@pytest.mark.parametrize("confirmation", [1, 1.0], ids=["integer", "float"])
def test_numeric_confirmation_is_rejected_without_mutation_and_boolean_retry_succeeds(confirmation):
    run = td_run()
    run_id = run["run_id"]
    url = f"/api/runs/{run_id}/td/reviews"
    command_id = "explicit-human-confirmation"
    checkpoint_before = api_main.workflow._snapshot(run_id)
    commands_before = set(api_main.runner._used_command_ids[run_id])

    response = client.post(
        url, json=td_review_body(run, command_id, user_confirmed=confirmation)
    )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_td_review"}}
    assert client.get(f"/api/runs/{run_id}").json() == run
    assert api_main.workflow._snapshot(run_id) == checkpoint_before
    assert api_main.runner._used_command_ids[run_id] == commands_before

    accepted = client.post(url, json=td_review_body(run, command_id, user_confirmed=True))

    assert accepted.status_code == 200
    reviewed = accepted.json()
    assert reviewed["td_review"]["status"] == "ready"
    assert len(reviewed["td_review_records"]) == len(run["td_review_records"]) + 1
    assert reviewed["td_review_records"][-1]["user_confirmed"] is True
    assert reviewed["td_review_records"][-1]["command_id"] == command_id
    assert api_main.runner._used_command_ids[run_id] == commands_before | {command_id}
    assert api_main.workflow.gate_key(run_id) != checkpoint_before.values["gate_key"]

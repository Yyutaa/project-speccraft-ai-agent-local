from fastapi.testclient import TestClient
from governance_helpers import clarification_body, td_review_body

from apps.api.main import app

client = TestClient(app)


def answer_all_clarifications(created: dict) -> dict:
    response = client.post(
        f"/api/runs/{created['run_id']}/clarifications/answers",
        json=clarification_body(created, "run-api-test-command"),
    )
    assert response.status_code == 200
    return response.json()


def create_prd_ready_run(requirement: str) -> dict:
    waiting = client.post(
        "/api/runs", json={"governance_contract_version": 2, "requirement": requirement}
    ).json()
    return answer_all_clarifications(waiting)


def prd_approval_body(run: dict) -> dict:
    return {
        "governance_contract_version": 2,
        "revision": run["prd_draft"]["revision"],
        "content_hash": run["prd_draft"]["content_hash"],
        "actor": "测试用户",
        "rationale": "已审阅当前 PRD 内容",
    }


def td_approval_body(run: dict, revision: int | None = None) -> dict:
    return {
        "governance_contract_version": 2,
        "revision": revision or run["td_draft"]["revision"],
        "content_hash": run["td_draft"]["content_hash"],
        "actor": "技术审阅人",
        "rationale": "已审阅当前 TD 内容",
        "review_id": run["td_review"]["current_review_id"] or "missing-review",
        "expected_review_revision": run["td_review"]["review_revision"],
    }


def test_run_api_happy_path_returns_each_server_owned_state() -> None:
    created_response = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "导出大文件时显示进度。",
        },
    )

    assert created_response.status_code == 201
    created = created_response.json()
    run_id = created["run_id"]
    assert created["status"] == "awaiting_clarification"
    assert created["prd_draft"] is None
    assert created["clarification_batch"] is not None
    assert created["td_draft"] is None
    assert created["delivery_spec"] is None

    read_response = client.get(f"/api/runs/{run_id}")
    assert read_response.status_code == 200
    assert read_response.json() == created

    created = answer_all_clarifications(created)
    assert created["status"] == "prd_awaiting_approval"
    assert created["prd_draft"] is not None

    prd_response = client.post(
        f"/api/runs/{run_id}/approvals/prd",
        json=prd_approval_body(created),
    )
    assert prd_response.status_code == 200
    after_prd = prd_response.json()
    assert after_prd["status"] == "td_awaiting_approval"
    assert after_prd["prd_approval"]["revision"] == 1
    assert after_prd["design_authority"] is not None
    assert after_prd["td_blueprint"] is not None
    assert after_prd["td_draft"] is not None
    assert after_prd["delivery_spec"] is None

    review_response = client.post(
        f"/api/runs/{run_id}/td/reviews", json=td_review_body(after_prd)
    )
    assert review_response.status_code == 200
    after_prd = review_response.json()
    td_response = client.post(
        f"/api/runs/{run_id}/approvals/td",
        json=td_approval_body(after_prd),
    )
    assert td_response.status_code == 200
    completed = td_response.json()
    assert completed["status"] == "completed"
    assert completed["delivery_spec"]["run_id"] == run_id
    assert completed["delivery_spec"]["prd"]["revision"] == 1
    assert completed["delivery_spec"]["td"]["revision"] == 1
    assert {item["artifact"]["kind"] for item in completed["artifact_envelopes"]} == {
        "prd",
        "td",
        "delivery_spec",
    }


def test_td_approval_before_prd_is_rejected_without_state_change() -> None:
    created = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement": "导出大文件时显示进度。",
        },
    ).json()
    run_id = created["run_id"]

    response = client.post(
        f"/api/runs/{run_id}/approvals/td",
        json={
            "governance_contract_version": 2,
            "revision": 1,
            "content_hash": "0" * 64,
            "actor": "技术审阅人",
            "rationale": "越序审批",
            "review_id": "missing-review",
            "expected_review_revision": 0,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_run_transition"
    assert client.get(f"/api/runs/{run_id}").json() == created


def test_stale_revision_is_rejected_without_state_change() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    run_id = created["run_id"]

    response = client.post(
        f"/api/runs/{run_id}/approvals/prd",
        json={**prd_approval_body(created), "revision": 2},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "revision_conflict"
    assert client.get(f"/api/runs/{run_id}").json() == created


def test_stale_td_revision_is_rejected_without_state_change() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    run_id = created["run_id"]
    awaiting_td = client.post(
        f"/api/runs/{run_id}/approvals/prd", json=prd_approval_body(created)
    ).json()

    response = client.post(
        f"/api/runs/{run_id}/approvals/td",
        json=td_approval_body(awaiting_td, revision=2),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "revision_conflict"
    assert client.get(f"/api/runs/{run_id}").json() == awaiting_td


def test_repeated_approval_is_rejected_and_run_remains_unchanged() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    run_id = created["run_id"]
    url = f"/api/runs/{run_id}/approvals/prd"
    body = prd_approval_body(created)
    accepted = client.post(url, json=body)
    assert accepted.status_code == 200

    rejected = client.post(url, json=body)

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "invalid_run_transition"
    assert client.get(f"/api/runs/{run_id}").json() == accepted.json()


def test_repeated_td_approval_is_rejected_and_completed_run_remains_unchanged() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    run_id = created["run_id"]
    client.post(f"/api/runs/{run_id}/approvals/prd", json=prd_approval_body(created))
    url = f"/api/runs/{run_id}/approvals/td"
    awaiting_td = client.get(f"/api/runs/{run_id}").json()
    review_response = client.post(
        f"/api/runs/{run_id}/td/reviews", json=td_review_body(awaiting_td)
    )
    assert review_response.status_code == 200
    awaiting_td = review_response.json()
    accepted = client.post(url, json=td_approval_body(awaiting_td))
    assert accepted.status_code == 200

    rejected = client.post(url, json=td_approval_body(awaiting_td))

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "invalid_run_transition"
    assert client.get(f"/api/runs/{run_id}").json() == accepted.json()


def test_unknown_run_is_not_found_and_blank_requirement_is_invalid() -> None:
    missing = client.get("/api/runs/does-not-exist")
    blank = client.post("/api/runs", json={"governance_contract_version": 2, "requirement": "  "})

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "run_not_found"
    assert blank.status_code == 422


def test_prd_section_revision_then_approval_binds_current_hash() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    run_id = created["run_id"]
    draft = created["prd_draft"]
    response = client.post(
        f"/api/runs/{run_id}/prd/revisions",
        json={
            "governance_contract_version": 2,
            "expected_revision": draft["revision"],
            "expected_content_hash": draft["content_hash"],
            "section_id": "acceptance",
            "replacement_body": "用户能看到导出进度并得到完成提示。",
            "feedback": "明确可观察的验收结果",
        },
    )
    assert response.status_code == 200
    revised = response.json()
    assert revised["prd_draft"]["revision"] == 2
    assert revised["prd_draft"]["content_hash"] != draft["content_hash"]
    assert len(revised["prd_revisions"]) == 2

    approved = client.post(f"/api/runs/{run_id}/approvals/prd", json=prd_approval_body(revised))
    assert approved.status_code == 200
    assert approved.json()["prd_approval"]["content_hash"] == revised["prd_draft"]["content_hash"]


def test_prd_hash_conflict_and_frozen_revision_leave_run_unchanged() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    run_id = created["run_id"]
    wrong_hash = "0" * 64
    rejected = client.post(
        f"/api/runs/{run_id}/approvals/prd",
        json={**prd_approval_body(created), "content_hash": wrong_hash},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "content_hash_conflict"
    assert client.get(f"/api/runs/{run_id}").json() == created

    approved = client.post(
        f"/api/runs/{run_id}/approvals/prd", json=prd_approval_body(created)
    ).json()
    rejected_revision = client.post(
        f"/api/runs/{run_id}/prd/revisions",
        json={
            "governance_contract_version": 2,
            "expected_revision": 1,
            "expected_content_hash": created["prd_draft"]["content_hash"],
            "section_id": "acceptance",
            "replacement_body": "审批后不允许修改。",
            "feedback": "试图越权修改",
        },
    )
    assert rejected_revision.status_code == 409
    assert rejected_revision.json()["detail"]["code"] == "invalid_run_transition"
    assert client.get(f"/api/runs/{run_id}").json() == approved


def test_prd_revision_cannot_inject_another_section_heading() -> None:
    created = create_prd_ready_run("导出大文件时显示进度。")
    draft = created["prd_draft"]
    response = client.post(
        f"/api/runs/{created['run_id']}/prd/revisions",
        json={
            "governance_contract_version": 2,
            "expected_revision": draft["revision"],
            "expected_content_hash": draft["content_hash"],
            "section_id": "acceptance",
            "replacement_body": "可验收。\n## 伪造章节\n不应写入。",
            "feedback": "尝试跨章节修改",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_prd_revision"
    assert client.get(f"/api/runs/{created['run_id']}").json() == created


def test_api_returns_auditable_sources_and_rejects_paths_outside_the_sample_root() -> None:
    created_response = client.post(
        "/api/runs",
        json={
            "governance_contract_version": 2,
            "requirement_path": "requirements/large-excel-import.md",
            "context_mode": "indexed_readonly",
        },
    )
    created = created_response.json()

    assert created_response.status_code == 201
    assert created["source_snapshot"]["source"]["source_type"] == "requirement_file"
    assert created["source_snapshot"]["normalized_path"] == "requirements/large-excel-import.md"
    assert len(created["source_snapshot"]["sha256"]) == 64
    assert created["repository_binding"]["permission"] == "read_only"
    assert created["harness_context"]["entries"]
    assert created["harness_context"]["sha256"]

    rejected = client.post(
        "/api/runs",
        json={"governance_contract_version": 2, "requirement_path": "../../README.md"},
    )

    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "path_outside_root"

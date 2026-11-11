"""Quality patch HTTP command preserves the Runner's state boundary."""

from deliveryflow_contracts.quality import QualityRiskAcceptanceRequest
from deliveryflow_speccraft.workflow import RunWorkflow
from fastapi.testclient import TestClient
from test_td_quality import patch_request, quality_run
from test_td_runner import runner

from apps.api import main as api_main


def test_quality_patch_api_rejects_stale_hash_and_returns_failed_attempt(
    monkeypatch,
) -> None:
    subject = runner()
    run = quality_run(subject)
    monkeypatch.setattr(api_main, "workflow", RunWorkflow(subject))
    client = TestClient(api_main.app)
    path = f"/api/runs/{run.run_id}/td/issues/patch"

    stale = client.post(
        path,
        json=patch_request(
            run,
            body="fixed",
            content_hash="0" * 64,
        ).model_dump(),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "content_hash_conflict"
    assert subject.get_run(run.run_id).quality_patch_attempts == ()

    failed = client.post(path, json=patch_request(run, body="still TODO").model_dump())
    assert failed.status_code == 200
    assert failed.json()["td_draft"]["content_hash"] == run.td_draft.content_hash
    assert failed.json()["quality_patch_attempts"][0]["outcome"] == "rejected"

    fixed = client.post(
        path,
        json=patch_request(
            subject.get_run(run.run_id),
            body="fixed",
            command_id="patch-2",
        ).model_dump(),
    )
    assert fixed.status_code == 200
    assert fixed.json()["quality_patch_attempts"][-1]["outcome"] == "committed"
    assert fixed.json()["quality_gate"]["status"] == "ready"


def test_risk_acceptance_api_refuses_blocker(monkeypatch) -> None:
    subject = runner()
    run = quality_run(subject)
    monkeypatch.setattr(api_main, "workflow", RunWorkflow(subject))
    issue = next(
        item for item in run.quality_issues if item.rule_id == "td.placeholder"
    )
    response = TestClient(api_main.app).post(
        f"/api/runs/{run.run_id}/td/issues/accept-risk",
        json=QualityRiskAcceptanceRequest(
            governance_contract_version=2,
            command_id="waive-blocker-api",
            issue_id=issue.issue_id,
            actor_claim="reviewer",
            rationale="想先通过",
            disclosure_location="TD 风险章节",
            expected_td_revision=run.td_draft.revision,
            expected_td_content_hash=run.td_draft.content_hash,
        ).model_dump(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "quality_risk_not_acceptable"
    assert subject.get_run(run.run_id) == run

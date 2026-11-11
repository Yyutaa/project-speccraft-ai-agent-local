"""Deterministic quality findings and bounded patch semantics."""

from hashlib import sha256
from pathlib import Path

import pytest
from deliveryflow_contracts.quality import (
    QualityIssueRecord,
    QualityPatchRequest,
    QualityRiskAcceptanceRequest,
)
from deliveryflow_contracts.td import TdRevisionRequest, TdSectionId
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    GovernanceError,
    RunRunner,
)
from deliveryflow_speccraft.td_quality import apply_quality_patch, discover_td_quality
from test_td_runner import approve_prd, prd_ready, runner

ROOT = Path(__file__).parent.parent


def quality_run(subject: RunRunner):
    run = approve_prd(subject, prd_ready(subject))
    assert run.td_draft is not None and run.td_review is not None
    return subject.revise_td(
        run.run_id,
        TdRevisionRequest(
            governance_contract_version=2,
            command_id="manual-todo",
            section_id="frontend",
            replacement_body="TODO",
            feedback="标出未完成项",
            actor_claim="reviewer",
            expected_td_revision=run.td_draft.revision,
            expected_td_content_hash=run.td_draft.content_hash,
            expected_review_revision=run.td_review.review_revision,
        ),
    )


def patch_request(
    run, *, body: str, command_id: str = "patch-1", content_hash: str | None = None
):
    issue = next(
        item for item in run.quality_issues if item.rule_id == "td.placeholder"
    )
    return QualityPatchRequest(
        governance_contract_version=2,
        command_id=command_id,
        issue_id=issue.issue_id,
        section_id="frontend",
        replacement_body=body,
        actor_claim="reviewer",
        expected_td_revision=run.td_draft.revision,
        expected_td_content_hash=content_hash or run.td_draft.content_hash,
        expected_review_revision=run.td_review.review_revision,
    )


def test_same_finding_is_one_issue_and_reopens_after_resolution() -> None:
    subject = runner()
    run = quality_run(subject)
    issue = next(
        item for item in run.quality_issues if item.rule_id == "td.placeholder"
    )
    assert discover_td_quality(run.td_draft.content)[0].issue_id == issue.issue_id
    fixed = subject.patch_td_issue(run.run_id, patch_request(run, body="fixed"))
    assert (
        next(
            item for item in fixed.quality_issues if item.issue_id == issue.issue_id
        ).status
        == "resolved"
    )
    reopened = subject.revise_td(
        fixed.run_id,
        TdRevisionRequest(
            governance_contract_version=2,
            command_id="reintroduce-todo",
            section_id="frontend",
            replacement_body="TODO",
            feedback="检查重开",
            actor_claim="reviewer",
            expected_td_revision=fixed.td_draft.revision,
            expected_td_content_hash=fixed.td_draft.content_hash,
            expected_review_revision=fixed.td_review.review_revision,
        ),
    )
    matches = [
        item for item in reopened.quality_issues if item.issue_id == issue.issue_id
    ]
    assert len(matches) == 1 and matches[0].status == "reopened"


def test_patch_commits_only_when_target_and_regression_checks_pass() -> None:
    source = "# TD\n## A\nTODO\n## B\nstable"
    expected_hash = sha256(source.encode()).hexdigest()
    result = apply_quality_patch(
        source,
        "A",
        "fixed",
        expected_hash=expected_hash,
        target_check=lambda text: "TODO" not in text,
        regression_check=lambda text: "## B\nstable" in text,
    )
    assert result.committed and "## A\nfixed" in result.content
    rejected = apply_quality_patch(
        source,
        "A",
        "still TODO",
        expected_hash=expected_hash,
        target_check=lambda text: "TODO" not in text,
        regression_check=lambda text: True,
    )
    assert not rejected.committed and rejected.content == source
    regressed = apply_quality_patch(
        source,
        "A",
        "fixed",
        expected_hash=expected_hash,
        target_check=lambda text: "TODO" not in text,
        regression_check=lambda text: False,
    )
    assert not regressed.committed and regressed.reason == "regression_detected"
    assert regressed.content == source


def test_quality_contract_rejects_invalid_status_and_stale_patch_shape() -> None:
    with pytest.raises(ValueError):
        QualityIssueRecord(
            issue_id="issue-1",
            validator_id="td_document",
            rule_id="td.placeholder",
            section_id="frontend",
            authority_ref="",
            evidence="TODO",
            severity="blocker",
            status="resolved",
            attempts=3,
            last_failure="target_still_present",
        )
    with pytest.raises(ValueError):
        QualityPatchRequest(
            governance_contract_version=2,
            command_id="patch-1",
            issue_id="issue-1",
            section_id="frontend",
            replacement_body="",
            actor_claim="reviewer",
            expected_td_revision=1,
            expected_td_content_hash="0" * 64,
            expected_review_revision=0,
        )


def test_manual_td_revision_discovers_persistent_quality_issue() -> None:
    subject = runner()
    revised = quality_run(subject)
    assert any(issue.rule_id == "td.placeholder" for issue in revised.quality_issues)
    assert revised.quality_gate is not None
    assert revised.quality_gate.status == "continue"
    failed = subject.patch_td_issue(
        revised.run_id, patch_request(revised, body="still TODO")
    )
    assert failed.td_draft == revised.td_draft
    assert failed.quality_issues[0].attempts == 1
    fixed = subject.patch_td_issue(failed.run_id, patch_request(failed, body="fixed", command_id="patch-2"))
    assert fixed.td_draft.revision == revised.td_draft.revision + 1
    assert fixed.quality_gate.status == "ready"
    assert fixed.td_review.status == "stale"


def test_patch_rejects_stale_hash_without_recording_attempt() -> None:
    subject = runner()
    run = quality_run(subject)
    with pytest.raises(ContentHashConflict):
        subject.patch_td_issue(
            run.run_id, patch_request(run, body="fixed", content_hash="0" * 64)
        )
    assert subject.get_run(run.run_id).quality_patch_attempts == ()
    assert subject.get_run(run.run_id).td_draft == run.td_draft


def test_patch_rejects_wrong_section_and_rolls_back_structural_regression() -> None:
    subject = runner()
    run = quality_run(subject)
    wrong = patch_request(run, body="fixed").model_copy(
        update={"section_id": TdSectionId.BACKEND}
    )
    with pytest.raises(GovernanceError, match="quality_issue_not_repairable"):
        subject.patch_td_issue(run.run_id, wrong)
    assert subject.get_run(run.run_id).quality_patch_attempts == ()
    failed = subject.patch_td_issue(
        run.run_id,
        patch_request(
            run,
            body="fixed\n## 未计划章节\n新增结构",
            command_id="bad-structure",
        ),
    )
    assert failed.td_draft == run.td_draft
    assert failed.quality_patch_attempts[-1].reason == "section_set_changed"


def test_failed_patch_budget_blocks_more_attempts_and_preserves_td() -> None:
    subject = runner()
    run = quality_run(subject)
    baseline = run.td_draft
    for index in range(3):
        run = subject.patch_td_issue(
            run.run_id,
            patch_request(run, body="still TODO", command_id=f"failed-{index}"),
        )
    assert run.td_draft == baseline
    assert run.quality_gate.status == "diagnose"
    assert run.quality_issues[0].status == "failed"
    assert "patch_td_issue" not in run.available_commands
    with pytest.raises(Exception, match="quality_issue_not_repairable"):
        subject.patch_td_issue(
            run.run_id, patch_request(run, body="fixed", command_id="too-late")
        )
    assert len(subject.get_run(run.run_id).quality_patch_attempts) == 3


def test_quality_issue_and_failed_attempt_survive_restart(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"

    def persistent_runner() -> RunRunner:
        return RunRunner(
            RepositoryHarness(
                ROOT / "examples/speccraft/repositories/exportflow-sample"
            ),
            ROOT / "learning-assets/authoring-pack/v1/prd",
            td_authoring_directory=ROOT / "learning-assets/authoring-pack/v1/td",
            database_path=database,
        )

    subject = persistent_runner()
    run = quality_run(subject)
    failed = subject.patch_td_issue(run.run_id, patch_request(run, body="still TODO"))
    reopened = persistent_runner().get_run(run.run_id)
    assert reopened.quality_issues == failed.quality_issues
    assert reopened.quality_patch_attempts == failed.quality_patch_attempts
    assert reopened.quality_gate == failed.quality_gate


def test_missing_chapter_authority_reference_blocks_quality_gate() -> None:
    subject = runner()
    run = approve_prd(subject, prd_ready(subject))
    assert run.td_draft is not None and run.td_review is not None
    assert run.quality_gate is not None and run.quality_gate.status == "ready"
    revised = subject.revise_td(
        run.run_id,
        TdRevisionRequest(
            governance_contract_version=2,
            command_id="remove-api-reference",
            section_id="api_events_errors",
            replacement_body="接口约束待人工细化。",
            feedback="检查章节引用",
            actor_claim="reviewer",
            expected_td_revision=run.td_draft.revision,
            expected_td_content_hash=run.td_draft.content_hash,
            expected_review_revision=run.td_review.review_revision,
        ),
    )
    assert any(issue.rule_id == "td.authority_ref" for issue in revised.quality_issues)
    assert (
        revised.quality_gate is not None and revised.quality_gate.status == "continue"
    )
    assert "approve_td" not in revised.available_commands


def test_only_current_major_issue_can_be_accepted_with_risk_evidence() -> None:
    subject = runner()
    run = approve_prd(subject, prd_ready(subject))
    uncertain = subject.revise_td(
        run.run_id,
        TdRevisionRequest(
            governance_contract_version=2,
            command_id="mark-uncertain",
            section_id="frontend",
            replacement_body="待核实：前端进度状态边界。",
            feedback="标出技术不确定项",
            actor_claim="reviewer",
            expected_td_revision=run.td_draft.revision,
            expected_td_content_hash=run.td_draft.content_hash,
            expected_review_revision=run.td_review.review_revision,
        ),
    )
    issue = next(
        item for item in uncertain.quality_issues if item.rule_id == "td.uncertain"
    )
    assert issue.severity == "major" and uncertain.quality_gate.status == "continue"
    request = QualityRiskAcceptanceRequest(
        governance_contract_version=2,
        command_id="accept-risk",
        issue_id=issue.issue_id,
        actor_claim="technical-owner",
        rationale="已有人工验证计划",
        disclosure_location="TD 发布、迁移、回滚与风险章节",
        expected_td_revision=uncertain.td_draft.revision,
        expected_td_content_hash=uncertain.td_draft.content_hash,
    )
    with pytest.raises(ContentHashConflict):
        subject.accept_td_quality_risk(
            uncertain.run_id,
            request.model_copy(update={"expected_td_content_hash": "0" * 64}),
        )
    accepted = subject.accept_td_quality_risk(uncertain.run_id, request)
    assert accepted.quality_gate.status == "ready"
    assert (
        accepted.quality_risk_acceptances[-1].disclosure_label
        == request.disclosure_location
    )
    assert (
        next(
            item for item in accepted.quality_issues if item.issue_id == issue.issue_id
        ).status
        == "accepted"
    )
    revised = subject.revise_td(
        accepted.run_id,
        TdRevisionRequest(
            governance_contract_version=2,
            command_id="risk-revision",
            section_id="frontend",
            replacement_body="待核实：另一项前端边界。",
            feedback="修订技术边界",
            actor_claim="reviewer",
            expected_td_revision=accepted.td_draft.revision,
            expected_td_content_hash=accepted.td_draft.content_hash,
            expected_review_revision=accepted.td_review.review_revision,
        ),
    )
    assert revised.quality_gate.status == "continue"
    assert (
        next(
            item for item in revised.quality_issues if item.issue_id == issue.issue_id
        ).status
        == "reopened"
    )


def test_blocker_risk_acceptance_is_rejected_without_state_change() -> None:
    subject = runner()
    run = quality_run(subject)
    issue = next(
        item for item in run.quality_issues if item.rule_id == "td.placeholder"
    )
    with pytest.raises(GovernanceError, match="quality_risk_not_acceptable"):
        subject.accept_td_quality_risk(
            run.run_id,
            QualityRiskAcceptanceRequest(
                governance_contract_version=2,
                command_id="waive-blocker",
                issue_id=issue.issue_id,
                actor_claim="reviewer",
                rationale="想先通过",
                disclosure_location="TD 风险章节",
                expected_td_revision=run.td_draft.revision,
                expected_td_content_hash=run.td_draft.content_hash,
            ),
        )
    assert subject.get_run(run.run_id) == run

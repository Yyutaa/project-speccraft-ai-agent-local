from hashlib import sha256
from pathlib import Path

import pytest
from deliveryflow_contracts.prd import (
    PrdApprovalRequest,
    PrdRevisionRequest,
    PrdSectionId,
)
from deliveryflow_contracts.runs import CreateRunRequest, RunStatus
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    InMemoryRunner,
    InvalidRunTransition,
    PrdNotReady,
    RevisionConflict,
)
from governance_helpers import clarification_request

ROOT = Path(__file__).parent.parent


def ready_run() -> tuple[InMemoryRunner, object]:
    runner = InMemoryRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
    )
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
    )
    assert waiting.clarification_batch is not None
    ready = runner.submit_clarification(
        waiting.run_id,
        clarification_request(waiting, "prd-revision-test-answer"),
    )
    return runner, ready


def approval(run) -> PrdApprovalRequest:
    assert run.prd_draft is not None
    return PrdApprovalRequest(
        governance_contract_version=2,
        revision=run.prd_draft.revision,
        content_hash=run.prd_draft.content_hash,
        actor="本地用户",
        rationale="已审阅并接受该版本",
    )


def test_prd_is_built_from_blueprint_then_one_section_can_be_revised_and_frozen() -> None:
    runner, ready = ready_run()
    assert ready.prd_draft is not None
    assert ready.prd_blueprint is not None
    assert ready.prd_readiness is not None and ready.prd_readiness.ready
    assert ready.status is RunStatus.PRD_AWAITING_APPROVAL
    assert len(ready.prd_blueprint.sections) == 8
    assert len(ready.prd_revisions) == 1
    assert ready.td_draft is None
    assert (
        ready.prd_draft.content_hash == sha256(ready.prd_draft.content.encode("utf-8")).hexdigest()
    )

    revised = runner.revise_prd(
        ready.run_id,
        PrdRevisionRequest(
            governance_contract_version=2,
            expected_revision=1,
            expected_content_hash=ready.prd_draft.content_hash,
            section_id=PrdSectionId.ACTORS,
            replacement_body="- 仅管理员使用导出功能。",
            feedback="明确使用角色",
        ),
    )
    assert revised.prd_draft is not None
    assert revised.prd_draft.revision == 2
    assert revised.prd_draft.content_hash != ready.prd_draft.content_hash
    assert len(revised.prd_revisions) == 2
    assert revised.ledger == ready.ledger
    assert revised.prd_blueprint == ready.prd_blueprint
    assert revised.td_draft is None
    assert "## 角色与场景\n- 仅管理员使用导出功能。" in revised.prd_draft.content
    assert (
        revised.prd_draft.content.split("## 角色与场景\n")[0]
        == (ready.prd_draft.content.split("## 角色与场景\n")[0])
    )
    assert (
        revised.prd_draft.content.split("## 功能与核心业务流程")[1]
        == (ready.prd_draft.content.split("## 功能与核心业务流程")[1])
    )

    frozen = runner.approve_prd(revised.run_id, approval(revised))
    assert frozen.prd_approval is not None
    assert frozen.prd_approval.revision == 2
    assert frozen.prd_approval.content_hash == revised.prd_draft.content_hash
    assert frozen.prd_approval.actor == "本地用户"
    assert frozen.status is RunStatus.TD_AWAITING_APPROVAL

    with pytest.raises(InvalidRunTransition):
        runner.revise_prd(
            revised.run_id,
            PrdRevisionRequest(
                governance_contract_version=2,
                expected_revision=2,
                expected_content_hash=revised.prd_draft.content_hash,
                section_id=PrdSectionId.ACTORS,
                replacement_body="- 再次改动。",
                feedback="批准后尝试修改",
            ),
        )
    assert runner.get_run(revised.run_id) == frozen


def test_stale_revision_and_wrong_hash_cannot_approve_current_prd() -> None:
    runner, ready = ready_run()
    assert ready.prd_draft is not None
    revised = runner.revise_prd(
        ready.run_id,
        PrdRevisionRequest(
            governance_contract_version=2,
            expected_revision=1,
            expected_content_hash=ready.prd_draft.content_hash,
            section_id=PrdSectionId.ACTORS,
            replacement_body="- 由管理员使用。",
            feedback="更新角色章节",
        ),
    )

    with pytest.raises(RevisionConflict):
        runner.approve_prd(revised.run_id, approval(ready))
    with pytest.raises(ContentHashConflict):
        runner.approve_prd(
            revised.run_id,
            approval(revised).model_copy(update={"content_hash": "0" * 64}),
        )
    assert runner.get_run(revised.run_id) == revised


def test_placeholder_revision_keeps_failure_evidence_and_blocks_approval() -> None:
    runner, ready = ready_run()
    assert ready.prd_draft is not None
    revised = runner.revise_prd(
        ready.run_id,
        PrdRevisionRequest(
            governance_contract_version=2,
            expected_revision=1,
            expected_content_hash=ready.prd_draft.content_hash,
            section_id=PrdSectionId.ACCEPTANCE,
            replacement_body="TODO",
            feedback="暂存未完成验收文字",
        ),
    )

    assert revised.prd_readiness is not None
    assert not revised.prd_readiness.ready
    assert any(issue.code == "placeholder" for issue in revised.prd_readiness.issues)
    with pytest.raises(PrdNotReady):
        runner.approve_prd(revised.run_id, approval(revised))
    assert runner.get_run(revised.run_id) == revised

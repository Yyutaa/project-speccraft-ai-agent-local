from pathlib import Path

import pytest
from deliveryflow_contracts.prd import PrdApprovalRequest
from deliveryflow_contracts.runs import (
    AvailableCommand,
    CreateRunRequest,
    RunStatus,
)
from deliveryflow_contracts.td import TdApprovalRequest
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import (
    InMemoryRunner,
    InvalidRunTransition,
    RevisionConflict,
)
from governance_helpers import clarification_request, td_review_request


def make_runner() -> InMemoryRunner:
    root = Path(__file__).parent.parent / "examples/speccraft/repositories/exportflow-sample"
    pack = Path(__file__).parent.parent / "learning-assets/authoring-pack/v1/prd"
    return InMemoryRunner(RepositoryHarness(root), pack)


def answer_clarification(runner: InMemoryRunner, run):
    assert run.clarification_batch is not None
    return runner.submit_clarification(
        run.run_id,
        clarification_request(run, "test-command"),
    )


def approval_request(run, revision: int | None = None) -> PrdApprovalRequest:
    assert run.prd_draft is not None
    return PrdApprovalRequest(
        governance_contract_version=2,
        revision=revision or run.prd_draft.revision,
        content_hash=run.prd_draft.content_hash,
        actor="测试用户",
        rationale="已审阅草稿",
    )


def td_approval_request(run, revision: int | None = None) -> TdApprovalRequest:
    assert run.td_draft is not None
    return TdApprovalRequest(
        governance_contract_version=2,
        revision=revision or run.td_draft.revision,
        content_hash=run.td_draft.content_hash,
        actor="技术审阅人",
        rationale="已审阅 TD",
        review_id=run.td_review.current_review_id or "missing-review",
        expected_review_revision=run.td_review.review_revision,
    )


def test_run_moves_from_prd_approval_to_td_approval_to_completion() -> None:
    runner = make_runner()
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
    )

    assert waiting.status is RunStatus.AWAITING_CLARIFICATION
    assert waiting.prd_draft is None
    assert waiting.clarification_batch is not None
    created = answer_clarification(runner, waiting)
    assert created.status is RunStatus.PRD_AWAITING_APPROVAL
    assert created.available_commands == (
        AvailableCommand.REVISE_PRD,
        AvailableCommand.APPROVE_PRD,
    )
    assert created.td_draft is None
    assert created.delivery_spec is None

    after_prd = runner.approve_prd(created.run_id, approval_request(created))
    assert after_prd.status is RunStatus.TD_AWAITING_APPROVAL
    assert after_prd.prd_approval is not None
    assert after_prd.prd_approval.revision == 1
    assert after_prd.td_draft is not None
    assert after_prd.delivery_spec is None

    after_prd = runner.record_td_review(created.run_id, td_review_request(after_prd))
    completed = runner.approve_td(created.run_id, td_approval_request(after_prd))
    assert completed.status is RunStatus.COMPLETED
    assert completed.td_approval is not None
    assert completed.delivery_spec is not None
    assert completed.delivery_spec.run_id == created.run_id
    assert completed.delivery_spec.prd.revision == 1
    assert completed.delivery_spec.td.revision == 1


def test_td_cannot_be_approved_before_prd_and_run_stays_unchanged() -> None:
    runner = make_runner()
    created = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
    )

    with pytest.raises(InvalidRunTransition):
        runner.approve_td(
            created.run_id,
            TdApprovalRequest(
                governance_contract_version=2,
                revision=1,
                content_hash="0" * 64,
                actor="技术审阅人",
                rationale="越序审批",
                review_id="missing-review",
                expected_review_revision=0,
            ),
        )

    assert runner.get_run(created.run_id) == created


def test_stale_prd_revision_is_rejected_without_advancing_run() -> None:
    runner = make_runner()
    created = answer_clarification(
        runner,
        runner.create_run(
            CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
        ),
    )

    with pytest.raises(RevisionConflict):
        runner.approve_prd(created.run_id, approval_request(created, revision=2))

    assert runner.get_run(created.run_id) == created


def test_stale_td_revision_is_rejected_without_completing_run() -> None:
    runner = make_runner()
    created = answer_clarification(
        runner,
        runner.create_run(
            CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
        ),
    )
    awaiting_td = runner.approve_prd(created.run_id, approval_request(created))

    with pytest.raises(RevisionConflict):
        runner.approve_td(created.run_id, td_approval_request(awaiting_td, revision=2))

    assert runner.get_run(created.run_id) == awaiting_td


def test_repeated_prd_approval_is_rejected_without_changing_td_draft() -> None:
    runner = make_runner()
    created = answer_clarification(
        runner,
        runner.create_run(
            CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
        ),
    )
    after_prd = runner.approve_prd(created.run_id, approval_request(created))

    with pytest.raises(InvalidRunTransition):
        runner.approve_prd(created.run_id, approval_request(created))

    assert runner.get_run(created.run_id) == after_prd


def test_repeated_td_approval_is_rejected_without_changing_completed_run() -> None:
    runner = make_runner()
    created = answer_clarification(
        runner,
        runner.create_run(
            CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
        ),
    )
    runner.approve_prd(created.run_id, approval_request(created))
    awaiting_td = runner.get_run(created.run_id)
    awaiting_td = runner.record_td_review(created.run_id, td_review_request(awaiting_td))
    completed = runner.approve_td(created.run_id, td_approval_request(awaiting_td))

    with pytest.raises(InvalidRunTransition):
        runner.approve_td(created.run_id, td_approval_request(awaiting_td))

    assert runner.get_run(created.run_id) == completed


def test_fake_provider_generates_same_drafts_for_same_requirement() -> None:
    runner = make_runner()

    first = answer_clarification(
        runner,
        runner.create_run(
            CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
        ),
    )
    second = answer_clarification(
        runner,
        runner.create_run(
            CreateRunRequest(governance_contract_version=2, requirement="导出时显示进度。")
        ),
    )
    assert first.prd_draft is not None
    assert second.prd_draft is not None
    first_completed = runner.approve_prd(first.run_id, approval_request(first))
    second_completed = runner.approve_prd(second.run_id, approval_request(second))

    assert first.prd_draft is not None
    assert second.prd_draft is not None
    assert first.prd_draft.content == second.prd_draft.content
    assert first_completed.td_draft is not None
    assert second_completed.td_draft is not None
    assert first_completed.td_draft.content == second_completed.td_draft.content

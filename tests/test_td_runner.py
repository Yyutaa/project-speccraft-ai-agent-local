from pathlib import Path

import pytest
from deliveryflow_contracts.facts import ClarificationAnswer, SubmitClarificationRequest
from deliveryflow_contracts.prd import PrdApprovalRequest
from deliveryflow_contracts.runs import AvailableCommand, CreateRunRequest, RunStatus
from deliveryflow_contracts.td import (
    AuthorityTopic,
    SubmitTechnicalDecisionsRequest,
    TdApprovalRequest,
    TechnicalDecision,
    TechnicalDecisionRequest,
)
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import InMemoryRunner, TdObligationConflict
from deliveryflow_speccraft.td_authoring import FakeTdAuthor, TdAuthorResult

ROOT = Path(__file__).parent.parent


def runner(td_author=None) -> InMemoryRunner:
    return InMemoryRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
        td_authoring_directory=ROOT / "learning-assets/authoring-pack/v1/td",
        td_author=td_author,
    )


def prd_ready(subject: InMemoryRunner):
    run = subject.create_run(CreateRunRequest(requirement="导出时显示进度。"))
    assert run.clarification_batch is not None
    return subject.submit_clarification(
        run.run_id,
        SubmitClarificationRequest(
            expected_revision=run.ledger.revision,
            command_id="answers-1",
            answers=tuple(
                ClarificationAnswer(
                    question_id=item.question_id,
                    selected_option_id=item.options[0].option_id,
                )
                for item in run.clarification_batch.proposals
                if item.gap_id in run.clarification_batch.blocking_gap_ids
            ),
        ),
    )


def approve_prd(subject: InMemoryRunner, run):
    assert run.prd_draft is not None
    return subject.approve_prd(
        run.run_id,
        PrdApprovalRequest(
            revision=run.prd_draft.revision,
            content_hash=run.prd_draft.content_hash,
            actor="product-owner",
            rationale="scope approved",
        ),
    )


def test_approved_prd_derives_authority_td_and_publishes_three_artifacts() -> None:
    subject = runner()
    awaiting_td = approve_prd(subject, prd_ready(subject))

    assert awaiting_td.status is RunStatus.TD_AWAITING_APPROVAL
    assert awaiting_td.design_authority is not None
    assert awaiting_td.td_blueprint is not None
    assert awaiting_td.td_draft is not None
    assert awaiting_td.td_draft.prd_content_hash == awaiting_td.prd_approval.content_hash
    assert awaiting_td.available_commands == (AvailableCommand.APPROVE_TD,)
    assert awaiting_td.delivery_spec is None

    completed = subject.approve_td(
        awaiting_td.run_id,
        TdApprovalRequest(
            revision=awaiting_td.td_draft.revision,
            content_hash=awaiting_td.td_draft.content_hash,
            actor="tech-owner",
            rationale="implementation design approved",
        ),
    )

    assert completed.status is RunStatus.COMPLETED
    assert completed.td_approval is not None
    assert completed.delivery_spec is not None
    assert completed.delivery_spec.prd.content_hash == completed.prd_draft.content_hash
    assert completed.delivery_spec.td.content_hash == completed.td_draft.content_hash
    assert {item.artifact.kind.value for item in completed.artifact_envelopes} == {
        "prd", "td", "delivery_spec",
    }
    assert all(item.approval is not None for item in completed.artifact_envelopes)
    assert completed.artifact_envelopes[0].approval.actor == "product-owner"
    assert completed.artifact_envelopes[-1].approval.actor == "tech-owner"


class ConflictingAuthor(FakeTdAuthor):
    def author(self, *args, **kwargs):
        result = super().author(*args, **kwargs)
        assert result.obligations is not None
        changed = result.obligations[0].model_copy(update={"statement": "扩大产品范围"})
        return TdAuthorResult(
            content=result.content,
            obligations=(changed, *result.obligations[1:]),
        )


def test_td_product_scope_change_is_rejected_without_publishing_and_keeps_prd_frozen() -> None:
    subject = runner(ConflictingAuthor())
    awaiting_td = approve_prd(subject, prd_ready(subject))
    assert awaiting_td.prd_approval is not None
    assert awaiting_td.td_draft is not None

    with pytest.raises(TdObligationConflict, match="frozen PRD obligation"):
        subject.approve_td(
            awaiting_td.run_id,
            TdApprovalRequest(
                revision=awaiting_td.td_draft.revision,
                content_hash=awaiting_td.td_draft.content_hash,
                actor="tech-owner",
                rationale="candidate review",
            ),
        )

    assert subject.get_run(awaiting_td.run_id) == awaiting_td


class DecisionAuthor(FakeTdAuthor):
    def author(self, blueprint, authority, obligations, pack, repository_constraints, decisions):
        if not decisions:
            return TdAuthorResult(decision_requests=(TechnicalDecisionRequest(
                request_id="tech-storage",
                topic=AuthorityTopic.DATA,
                question="选择临时文件存储方式",
                options=("local", "object-storage"),
                reason="仓库约束无法唯一确定",
            ),))
        return super().author(
            blueprint, authority, obligations, pack, repository_constraints, decisions
        )


def test_technical_choice_pauses_and_resumes_only_after_user_decision() -> None:
    subject = runner(DecisionAuthor())
    waiting = approve_prd(subject, prd_ready(subject))

    assert waiting.status is RunStatus.TD_AWAITING_DECISION
    assert waiting.td_draft is None
    assert waiting.available_commands == (AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,)

    resumed = subject.submit_technical_decisions(
        waiting.run_id,
        SubmitTechnicalDecisionsRequest(
            expected_prd_revision=waiting.prd_draft.revision,
            expected_prd_content_hash=waiting.prd_draft.content_hash,
            decisions=(TechnicalDecision(
                request_id="tech-storage",
                answer="local",
                actor="tech-owner",
            ),),
        ),
    )
    assert resumed.status is RunStatus.TD_AWAITING_APPROVAL
    assert resumed.td_draft is not None
    assert resumed.technical_decisions[0].answer == "local"

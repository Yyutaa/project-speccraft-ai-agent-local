import hashlib

import pytest
from deliveryflow_contracts.facts import (
    ClarificationAnswer,
    ClarificationBatch,
    ClarificationOption,
    ClarificationProposal,
    CompletenessResult,
    DecisionEvidence,
    FactDimension,
    FactKind,
    FactLedger,
    GapSignal,
    RequirementFact,
    SourceEvidence,
)
from governance_helpers import admitted_fact
from pydantic import ValidationError


def source_evidence() -> SourceEvidence:
    return SourceEvidence(
        sha256=hashlib.sha256(b"user said").hexdigest(),
        excerpt="user said",
    )


def decision_evidence(answer: str = "管理员") -> DecisionEvidence:
    return DecisionEvidence(
        actor_claim="test-user",
        rationale="已确认答案",
        batch_id="batch-1",
        question_id="gap-role",
        command_id="command-1",
        expected_revision=1,
        answer=answer,
    )


def test_fact_requires_source_evidence() -> None:
    with pytest.raises(ValidationError, match="source evidence"):
        RequirementFact(
            fact_id="fact-1",
            kind=FactKind.FACT,
            dimension=FactDimension.ROLE,
            claim="管理员使用系统",
        )


def test_contracts_reject_whitespace_only_claims_answers_and_option_labels() -> None:
    with pytest.raises(ValidationError):
        RequirementFact(
            fact_id="blank-fact",
            kind=FactKind.FACT,
            dimension=None,
            claim=" ",
            source=source_evidence(),
        )
    with pytest.raises(ValidationError):
        ClarificationOption(option_id="blank", label=" \n ")
    with pytest.raises(ValidationError):
        DecisionEvidence(
            actor_claim="test-user",
            rationale="已确认答案",
            batch_id="batch-1",
            question_id="gap-role",
            command_id="command-1",
            expected_revision=1,
            answer=" \n ",
        )


def test_decision_requires_user_decision_evidence() -> None:
    with pytest.raises(ValidationError, match="decision evidence"):
        RequirementFact(
            fact_id="decision-1",
            kind=FactKind.DECISION,
            dimension=FactDimension.ROLE,
            claim="管理员",
        )


def test_decision_claim_must_match_its_evidence_answer() -> None:
    with pytest.raises(ValidationError, match="claim must match decision evidence"):
        RequirementFact(
            fact_id="decision-1",
            kind=FactKind.DECISION,
            dimension=FactDimension.ROLE,
            claim="客户",
            decision_evidence=decision_evidence(),
        )


def test_recommendation_is_distinct_from_authoritative_ledger_fact() -> None:
    ledger = FactLedger(
        revision=1,
        facts=(admitted_fact(fact_id="fact-1", dimension=None, claim="用户希望导出报表"),),
    )

    assert ledger.authoritative_view == ("用户希望导出报表",)
    assert {fact.kind for fact in ledger.facts} == {FactKind.FACT}


def test_clarification_batch_must_cover_every_blocking_gap() -> None:
    gap = GapSignal(
        gap_id="gap-role",
        dimension=FactDimension.ROLE,
        blocking=True,
        reason="缺少使用角色",
        ledger_revision=1,
    )

    with pytest.raises(ValidationError, match="cover every blocking gap"):
        ClarificationBatch(
            batch_id="batch-1",
            revision=1,
            ledger_revision=1,
            gap_ids=(gap.gap_id,),
            blocking_gap_ids=(gap.gap_id,),
            proposals=(),
        )


def test_proposal_recommendation_must_name_an_available_option() -> None:
    with pytest.raises(ValidationError, match="recommended option"):
        ClarificationProposal(
            question_id="gap-role",
            gap_id="gap-role",
            question="谁使用？",
            options=({"option_id": "admin", "label": "管理员"},),
            recommended_option_id="customer",
            recommendation_reason="常见选择",
        )


def test_clarification_batch_rejects_proposals_for_unknown_gaps() -> None:
    with pytest.raises(ValidationError, match="refer to a known gap"):
        ClarificationBatch(
            batch_id="batch-1",
            revision=1,
            ledger_revision=1,
            gap_ids=("gap-role",),
            blocking_gap_ids=("gap-role",),
            proposals=(
                ClarificationProposal(
                    question_id="gap-workflow",
                    gap_id="gap-workflow",
                    question="流程是什么？",
                    options=({"option_id": "single", "label": "单步骤"},),
                ),
            ),
        )


def test_answer_requires_exactly_one_explicit_option_or_custom_answer() -> None:
    with pytest.raises(ValidationError):
        ClarificationAnswer(question_id="gap-role")
    with pytest.raises(ValidationError):
        ClarificationAnswer(
            question_id="gap-role",
            selected_option_id="admin",
            custom_answer="运营人员",
        )

    answer = ClarificationAnswer(question_id="gap-role", selected_option_id="admin")
    assert answer.selected_option_id == "admin"


def test_decision_evidence_is_bound_to_revision_and_explicit_command() -> None:
    fact = RequirementFact(
        fact_id="decision-1",
        kind=FactKind.DECISION,
        dimension=FactDimension.ROLE,
        claim="管理员",
        decision_evidence=decision_evidence(),
    )

    assert fact.decision_evidence is not None
    assert fact.decision_evidence.expected_revision == 1
    assert fact.decision_evidence.command_id == "command-1"


def test_authoritative_view_prefers_user_decision_over_conflicting_facts() -> None:
    ledger = FactLedger(
        revision=2,
        facts=(
            admitted_fact(fact_id="role-a", dimension=FactDimension.ROLE, claim="管理员使用"),
            admitted_fact(fact_id="role-b", dimension=FactDimension.ROLE, claim="客户使用"),
            RequirementFact(
                fact_id="role-decision",
                kind=FactKind.DECISION,
                dimension=FactDimension.ROLE,
                claim="管理员负责操作",
                decision_evidence=decision_evidence("管理员负责操作"),
            ),
        ),
    )

    assert ledger.authoritative_view == ("管理员负责操作",)


def test_completeness_result_is_clear_only_when_no_blocking_gaps_remain() -> None:
    complete = CompletenessResult(ledger_revision=2, gaps=())
    waiting = CompletenessResult(
        ledger_revision=2,
        gaps=(
            GapSignal(
                gap_id="gap-role",
                dimension=FactDimension.ROLE,
                blocking=True,
                reason="缺少使用角色",
                ledger_revision=2,
            ),
        ),
    )

    assert complete.is_complete
    assert not waiting.is_complete

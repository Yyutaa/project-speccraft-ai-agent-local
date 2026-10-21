import hashlib

import pytest
from deliveryflow_contracts.context import (
    ContextMode,
    HarnessContextSlice,
    RepositoryBinding,
    SourceRef,
    SourceSnapshot,
    SourceType,
)
from deliveryflow_contracts.facts import (
    ClarificationBatch,
    ClarificationOption,
    ClarificationProposal,
    CompletenessResult,
    FactDimension,
    FactKind,
    FactLedger,
    GapSignal,
    RequirementFact,
    SourceEvidence,
)
from deliveryflow_contracts.prd import (
    SECTION_TITLES,
    PrdApprovalReceipt,
    PrdBlueprint,
    PrdReadiness,
    PrdRevision,
    PrdSectionId,
    PrdSectionPlan,
)
from deliveryflow_contracts.runs import (
    AvailableCommand,
    CreateRunRequest,
    RunResponse,
    RunStatus,
)
from pydantic import ValidationError


def context_fields() -> dict[str, object]:
    source_hash = hashlib.sha256("需求".encode()).hexdigest()
    facts = tuple(
        RequirementFact(
            fact_id=f"fact-{dimension.value}",
            kind=FactKind.FACT,
            dimension=dimension,
            claim=f"已明确{dimension.value}",
            source=SourceEvidence(
                sha256=source_hash,
                excerpt="需求",
            ),
        )
        for dimension in FactDimension
    )
    return {
        "source_snapshot": SourceSnapshot(
            source=SourceRef(source_type=SourceType.INLINE_REQUIREMENT),
            sha256=hashlib.sha256("需求".encode()).hexdigest(),
            read_status="read",
            content="需求",
        ),
        "repository_binding": RepositoryBinding(
            repository_id="exportflow-sample",
            root_path="/sample",
            context_mode=ContextMode.GUIDE_ONLY,
        ),
        "harness_context": HarnessContextSlice(
            entries=(), sha256=hashlib.sha256(b"[]").hexdigest()
        ),
        "ledger": FactLedger(revision=1, facts=facts),
        "completeness": CompletenessResult(ledger_revision=1, gaps=()),
    }


def prd_fields() -> dict[str, object]:
    content = "# PRD"
    digest = hashlib.sha256(content.encode()).hexdigest()
    draft = PrdRevision(revision=1, content=content, content_hash=digest)
    return {
        "prd_blueprint": PrdBlueprint(
            ledger_revision=1,
            authoritative_fact_ids=tuple(f"fact-{dimension.value}" for dimension in FactDimension),
            sections=tuple(
                PrdSectionPlan(
                    section_id=section_id,
                    title=SECTION_TITLES[section_id],
                    applicable=True,
                    fact_ids=tuple(f"fact-{dimension.value}" for dimension in FactDimension)
                    if section_id is PrdSectionId.BACKGROUND else (),
                )
                for section_id in PrdSectionId
            ),
        ),
        "prd_revisions": (draft,),
        "prd_draft": draft,
        "prd_readiness": PrdReadiness(revision=1, content_hash=digest),
    }


def prd_receipt() -> PrdApprovalReceipt:
    return PrdApprovalReceipt(
        revision=1,
        content_hash=hashlib.sha256(b"# PRD").hexdigest(),
        actor="tester",
        rationale="reviewed",
    )


def test_create_run_request_preserves_raw_requirement_and_rejects_blank_text() -> None:
    request = CreateRunRequest(requirement="  导出大文件时显示进度。  ")

    assert request.requirement == "  导出大文件时显示进度。  "
    with pytest.raises(ValidationError):
        CreateRunRequest(requirement=" \n ")


def test_prd_waiting_run_has_revision_and_approval_commands() -> None:
    run = RunResponse(
        run_id="run-1",
        requirement="导出大文件时显示进度。",
        status=RunStatus.PRD_AWAITING_APPROVAL,
        available_commands=(AvailableCommand.REVISE_PRD, AvailableCommand.APPROVE_PRD),
        **prd_fields(),
        **context_fields(),
    )

    assert run.td_draft is None
    assert run.prd_approval is None
    assert run.delivery_spec is None


def test_completed_run_requires_both_approvals_and_delivery_spec() -> None:
    with pytest.raises(ValidationError):
        RunResponse(
            run_id="run-1",
            requirement="导出大文件时显示进度。",
            status=RunStatus.COMPLETED,
            prd_approval=prd_receipt(),
            available_commands=(),
            **prd_fields(),
            **context_fields(),
        )


def test_waiting_for_clarification_has_questions_but_no_prd() -> None:
    gap = GapSignal(
        gap_id="gap-role",
        dimension=FactDimension.ROLE,
        blocking=True,
        reason="缺少角色",
        ledger_revision=1,
    )
    run = RunResponse(
        run_id="run-clarify",
        requirement="需求",
        status="awaiting_clarification",
        prd_draft=None,
        available_commands=("submit_clarification",),
        source_snapshot=context_fields()["source_snapshot"],
        repository_binding=context_fields()["repository_binding"],
        harness_context=context_fields()["harness_context"],
        ledger=FactLedger(
            revision=1,
            facts=(RequirementFact(
                fact_id="source-1",
                kind=FactKind.FACT,
                dimension=None,
                claim="需求",
                source=SourceEvidence(
                    sha256=hashlib.sha256("需求".encode()).hexdigest(),
                    excerpt="需求",
                ),
            ),),
        ),
        completeness=CompletenessResult(ledger_revision=1, gaps=(gap,)),
        clarification_batch=ClarificationBatch(
            batch_id="batch-1",
            revision=1,
            ledger_revision=1,
            gap_ids=(gap.gap_id,),
            blocking_gap_ids=(gap.gap_id,),
            proposals=(ClarificationProposal(
                question_id=gap.gap_id,
                gap_id=gap.gap_id,
                question="谁使用？",
                options=(ClarificationOption(option_id="admin", label="管理员"),),
            ),),
        ),
    )

    assert run.prd_draft is None
    assert run.completeness.is_complete is False
    assert run.available_commands == ("submit_clarification",)


def test_waiting_for_clarification_cannot_include_a_prd_draft() -> None:
    with pytest.raises(ValidationError):
        RunResponse(
            run_id="run-clarify",
            requirement="创建导出工具",
            status="awaiting_clarification",
            prd_draft=PrdRevision(
                revision=1,
                content="# Premature PRD",
                content_hash=hashlib.sha256(b"# Premature PRD").hexdigest(),
            ),
            available_commands=("submit_clarification",),
            **context_fields(),
        )


def test_run_rejects_fact_evidence_not_bound_to_a_captured_source() -> None:
    fields = context_fields()
    ledger = fields["ledger"]
    facts = list(ledger.facts)
    facts[0] = facts[0].model_copy(update={
        "source": SourceEvidence(
            sha256=hashlib.sha256(b"unrelated source").hexdigest(),
            excerpt="not from this snapshot",
        )
    })

    with pytest.raises(ValidationError, match="source evidence must match a captured snapshot"):
        RunResponse(
            run_id="run-1",
            requirement="需求",
            status=RunStatus.PRD_AWAITING_APPROVAL,
            available_commands=(AvailableCommand.REVISE_PRD, AvailableCommand.APPROVE_PRD),
            **prd_fields(),
            **{**fields, "ledger": FactLedger(revision=1, facts=tuple(facts))},
        )

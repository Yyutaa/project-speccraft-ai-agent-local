"""S4: reference projections cannot become Author claims or product obligations."""

from pathlib import Path

import pytest
from deliveryflow_contracts.facts import SubmitClarificationRequest
from deliveryflow_contracts.prd import (
    PrdApprovalRequest,
    PrdRevisionRequest,
    PrdSectionId,
)
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_contracts.td import TdApprovalRequest
from deliveryflow_speccraft.prd_authoring import FakePrdAuthor
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import InMemoryRunner, RevisionConflict
from governance_helpers import clarification_body, td_review_request
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
PRODUCT_SECTIONS = {"scope", "actors", "journeys", "rules", "exceptions", "acceptance"}
BACKGROUND = "已确认的项目背景。"
KNOWLEDGE = "参考知识：执行前先检查。"
PENDING = "未确认的低风险展示假设。"
ACCEPTED = "人工确认的参考背景假设。"


class InspectingAuthor(FakePrdAuthor):
    """Exercise the real port while retaining exactly what crossed its boundary."""

    def author(self, task):
        self.received_claims = {item.claim_id: item.content for item in task.authoritative_claim_refs}
        return super().author(task)


def ready(tmp_path, *, with_support=True):
    (tmp_path / "knowledge").mkdir(exist_ok=True)
    (tmp_path / "knowledge/reference.txt").write_text(KNOWLEDGE, encoding="utf-8")
    for name in ("AGENTS.md", "README.md"):
        (tmp_path / name).write_text("只读工程参考。", encoding="utf-8")
    author = InspectingAuthor()
    subject = InMemoryRunner(
        RepositoryHarness(tmp_path), ROOT / "learning-assets/authoring-pack/v1/prd",
        prd_author=author,
    )
    request = {
        "governance_contract_version": 2,
        "requirement": BACKGROUND,
        "context_mode": "guide_only",
    }
    if with_support:
        request.update(
            knowledge_selections=[{
                "client_ref": "reference", "path": "knowledge/reference.txt",
                "start": 0, "end": len(KNOWLEDGE), "purpose": "人工审阅参考",
            }],
            assumptions=[{
                "client_ref": key, "statement": statement,
                "risk": "low", "product_impact": "none",
                "basis_refs": [{"kind": "candidate", "client_ref": "requirement_candidate"}],
            } for key, statement in (("pending", PENDING), ("accepted", ACCEPTED))],
        )
    run = subject.create_run(CreateRunRequest.model_validate(request))
    body = clarification_body(run)
    if with_support:
        assumption = run.assumptions[1]
        body["assumption_resolutions"] = [{
            "question_id": f"assumption-{assumption.assumption_id}",
            "assumption_id": assumption.assumption_id,
            "expected_assumption_revision": 1,
            "action": "accept", "rationale": "确认仅作参考",
        }]
    return subject, subject.submit_clarification(
        run.run_id, SubmitClarificationRequest.model_validate(body)
    ), author


def test_supporting_context_projects_validated_references_and_assumption_states(tmp_path):
    _, run, author = ready(tmp_path)
    sidebar = run.model_dump(mode="json")["prd_supporting_context"]

    assert sidebar["knowledge_citations"][0]["excerpt"] == KNOWLEDGE
    assert [(item["statement"], item["status"]) for item in sidebar["assumptions"]] == [
        (PENDING, "pending"), (ACCEPTED, "accepted"),
    ]
    assert "snapshot" not in sidebar["knowledge_citations"][0]
    assert set(author.received_claims) == set(run.prd_blueprint.authoritative_fact_ids)
    assert {BACKGROUND, "管理员", "单步骤流程", "按角色限制", "停止并提示错误", "使用可验证的验收条件"} == set(
        author.received_claims.values()
    )
    assert run.prd_draft is not None
    assert all(text not in run.prd_draft.content for text in (KNOWLEDGE, PENDING, ACCEPTED))


def test_supporting_context_tampering_is_rejected_at_run_contract_boundary(tmp_path):
    _, run, _ = ready(tmp_path)
    payload = run.model_dump()
    payload["prd_supporting_context"] = {"knowledge_citations": (), "assumptions": ()}
    with pytest.raises(ValidationError, match="supporting context"):
        RunResponse.model_validate(payload)


def test_supporting_context_does_not_change_exact_prd_body_or_hash(tmp_path):
    _, with_support, _ = ready(tmp_path)
    _, without_support, _ = ready(tmp_path, with_support=False)
    assert with_support.prd_draft.content == without_support.prd_draft.content
    assert with_support.prd_draft.content_hash == without_support.prd_draft.content_hash


def test_background_is_frozen_but_never_a_product_obligation_or_authority(tmp_path):
    subject, run, _ = ready(tmp_path)
    plans = {item.section_id: item for item in run.prd_blueprint.sections}
    background_fact = next(f for f in run.ledger.facts if f.dimension is None)
    workflow_fact = next(f for f in run.ledger.authoritative_facts if f.dimension == "workflow")
    assert plans[PrdSectionId.BACKGROUND].fact_ids == (background_fact.fact_id,)
    assert plans[PrdSectionId.SCOPE].fact_ids == (workflow_fact.fact_id,)
    assert plans[PrdSectionId.JOURNEYS].fact_ids == (workflow_fact.fact_id,)
    assert BACKGROUND in run.prd_draft.content
    approved = subject.approve_prd(run.run_id, PrdApprovalRequest(
        governance_contract_version=2, revision=run.prd_draft.revision,
        content_hash=run.prd_draft.content_hash, actor="product-owner", rationale="人工冻结",
    ))
    assert {item.prd_section_id.value for item in approved.td_draft.obligations} == PRODUCT_SECTIONS
    assert {fact_id for item in approved.td_draft.obligations for fact_id in item.source_fact_ids} == {
        fact.fact_id for fact in run.ledger.authoritative_facts if fact.dimension is not None
    }
    assert all(
        background_fact.fact_id not in item.source_fact_ids and BACKGROUND not in item.statement
        for item in (*approved.td_draft.obligations, *approved.design_authority.items)
    )
    assert all(
        set(item.source_prd_section_ids) <= PRODUCT_SECTIONS
        for item in approved.design_authority.items
    )
    approved = subject.record_td_review(approved.run_id, td_review_request(approved))
    completed = subject.approve_td(approved.run_id, TdApprovalRequest(
        governance_contract_version=2, revision=approved.td_draft.revision,
        content_hash=approved.td_draft.content_hash, actor="tech-owner", rationale="人工确认技术规格",
        review_id=approved.td_review.current_review_id,
        expected_review_revision=approved.td_review.review_revision,
    ))
    spec = completed.delivery_spec
    assert spec.prd.content_hash == run.prd_draft.content_hash
    assert spec.td.content_hash == approved.td_draft.content_hash
    assert {item.obligation_id for item in spec.obligations} == {
        f"prd-r1-{section}" for section in PRODUCT_SECTIONS
    }


def test_background_revision_changes_frozen_hash_and_rejects_old_approval(tmp_path):
    subject, run, _ = ready(tmp_path)
    revised = subject.revise_prd(run.run_id, PrdRevisionRequest(
        governance_contract_version=2,
        expected_revision=run.prd_draft.revision,
        expected_content_hash=run.prd_draft.content_hash,
        section_id=PrdSectionId.BACKGROUND,
        replacement_body=BACKGROUND + "补充背景说明。",
        feedback="人工核对背景说明",
    ))
    assert revised.prd_draft.content_hash != run.prd_draft.content_hash
    assert revised.prd_supporting_context == run.prd_supporting_context
    with pytest.raises(RevisionConflict):
        subject.approve_prd(run.run_id, PrdApprovalRequest(
            governance_contract_version=2, revision=run.prd_draft.revision,
            content_hash=run.prd_draft.content_hash, actor="product-owner", rationale="旧版背景",
        ))
    assert subject.get_run(run.run_id) == revised
    approved = subject.approve_prd(run.run_id, PrdApprovalRequest(
        governance_contract_version=2, revision=revised.prd_draft.revision,
        content_hash=revised.prd_draft.content_hash, actor="product-owner", rationale="核对完整正文",
    ))
    assert approved.prd_approval.content_hash == revised.prd_draft.content_hash
    assert approved.td_draft.prd_content_hash == revised.prd_draft.content_hash
    assert all(BACKGROUND not in item.statement for item in approved.td_draft.obligations)


def test_runner_rejects_nonexact_claim_set_before_calling_author(tmp_path, monkeypatch):
    from deliveryflow_contracts.prd import PrdBlueprint
    from deliveryflow_speccraft import runner as runner_module

    subject, _, author = ready(tmp_path)
    run = subject.create_run(CreateRunRequest(
        governance_contract_version=2, requirement=BACKGROUND, context_mode="guide_only",
    ))
    original_builder = runner_module.build_prd_blueprint

    def mismatched_blueprint(ledger):
        payload = original_builder(ledger).model_dump()
        payload["authoritative_fact_ids"] += ("support-reference",)
        payload["sections"][1]["fact_ids"] += ("support-reference",)
        return PrdBlueprint.model_validate(payload)

    def forbidden_author_call(*args, **kwargs):
        raise AssertionError("invalid authority input crossed the Author port")

    monkeypatch.setattr(runner_module, "build_prd_blueprint", mismatched_blueprint)
    monkeypatch.setattr(author, "author", forbidden_author_call)
    with pytest.raises(ValueError, match="exactly match"):
        subject.submit_clarification(
            run.run_id, SubmitClarificationRequest.model_validate(clarification_body(run))
        )
    assert subject.get_run(run.run_id) == run

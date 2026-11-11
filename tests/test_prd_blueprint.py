import pytest
from deliveryflow_contracts.facts import (
    DecisionEvidence,
    FactDimension,
    FactKind,
    FactLedger,
    RequirementFact,
)
from deliveryflow_contracts.prd import PrdSectionApplicability, PrdSectionId
from deliveryflow_speccraft.prd import (
    build_prd_blueprint,
    validate_prd_blueprint_snapshot,
)
from governance_helpers import admitted_fact


def sample_ledger() -> FactLedger:
    facts = [
        admitted_fact(fact_id="source-general", dimension=None, claim="导出时显示进度"),
        admitted_fact(
            fact_id="source-role", dimension=FactDimension.ROLE, claim="所有人"
        ),
    ]
    for dimension, claim in (
        (FactDimension.ROLE, "管理员"),
        (FactDimension.WORKFLOW, "选择文件后导出"),
        (FactDimension.PERMISSION, "仅管理员可以导出"),
        (FactDimension.FAILURE, "失败时提示并允许重试"),
        (FactDimension.ACCEPTANCE, "完成后可下载文件"),
    ):
        facts.append(
            RequirementFact(
                fact_id=f"decision-{dimension.value}",
                kind=FactKind.DECISION,
                dimension=dimension,
                claim=claim,
                decision_evidence=DecisionEvidence(
                    actor_claim="test-user",
                    rationale="已确认答案",
                    batch_id="batch-1",
                    question_id=f"question-{dimension.value}",
                    command_id="command-1",
                    expected_revision=1,
                    answer=claim,
                ),
            )
        )
    return FactLedger(revision=2, facts=tuple(facts))


def test_blueprint_references_every_authoritative_fact_and_excludes_overridden_source() -> (
    None
):
    ledger = sample_ledger()

    blueprint = build_prd_blueprint(ledger)

    assert tuple(fact.fact_id for fact in ledger.authoritative_facts) == (
        "source-general",
        "decision-role",
        "decision-workflow",
        "decision-permission",
        "decision-failure",
        "decision-acceptance",
    )
    assert blueprint.authoritative_fact_ids == tuple(
        fact.fact_id for fact in ledger.authoritative_facts
    )
    assert set(blueprint.sections[1].fact_ids) == {"source-general"}
    assert blueprint.sections[3].section_id is PrdSectionId.ACTORS
    assert blueprint.sections[3].fact_ids == ("decision-role",)
    assert "source-role" not in {
        fact_id for section in blueprint.sections for fact_id in section.fact_ids
    }


def test_blueprint_records_decision_refs_required_sections_and_input_snapshot() -> None:
    ledger = sample_ledger()
    blueprint = build_prd_blueprint(ledger)

    assert all(
        section.applicability is PrdSectionApplicability.REQUIRED
        for section in blueprint.sections
    )
    assert blueprint.sections[3].decision_ids == ("decision-role",)
    assert blueprint.sections[1].decision_ids == ()
    assert all(section.expected_content for section in blueprint.sections)
    assert blueprint.template_pack_version == "prd.v1"
    assert len(blueprint.input_digest) == 64
    assert build_prd_blueprint(ledger).content_hash() == blueprint.content_hash()
    assert build_prd_blueprint(ledger).input_digest == blueprint.input_digest
    changed = ledger.model_copy(update={"facts": ledger.facts[:-1]})
    assert build_prd_blueprint(changed).input_digest != blueprint.input_digest


def test_blueprint_snapshot_rejects_stale_input_and_tampered_plan() -> None:
    ledger = sample_ledger()
    blueprint = build_prd_blueprint(ledger)

    validate_prd_blueprint_snapshot(ledger, blueprint)
    with pytest.raises(ValueError, match="snapshot"):
        validate_prd_blueprint_snapshot(
            ledger.model_copy(update={"facts": ledger.facts[:-1]}), blueprint
        )
    sections = list(blueprint.sections)
    sections[3] = sections[3].model_copy(update={"expected_content": ("伪造",)})
    tampered = blueprint.model_copy(update={"sections": tuple(sections)})
    assert tampered.content_hash() != blueprint.content_hash()
    with pytest.raises(ValueError, match="snapshot"):
        validate_prd_blueprint_snapshot(ledger, tampered)

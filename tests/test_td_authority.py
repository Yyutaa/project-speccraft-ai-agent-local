from hashlib import sha256

import pytest
from deliveryflow_contracts.prd import (
    SECTION_TITLES,
    PrdApprovalReceipt,
    PrdBlueprint,
    PrdRevision,
    PrdSectionId,
    PrdSectionPlan,
)
from deliveryflow_contracts.td import AUTHORITY_TOPICS
from deliveryflow_speccraft.td import build_design_authority, extract_prd_obligations


def prd() -> PrdRevision:
    content = (
        "# 产品需求文档：导出\n\n"
        + "\n\n".join(
            f"## {title}\n{section_id.value} commitment"
            for section_id, title in SECTION_TITLES.items()
        )
        + "\n"
    )
    return PrdRevision(
        revision=2,
        content=content,
        content_hash=sha256(content.encode()).hexdigest(),
    )


def blueprint(revision: PrdRevision) -> PrdBlueprint:
    return PrdBlueprint(
        ledger_revision=3,
        authoritative_fact_ids=("fact-1",),
        sections=tuple(
            PrdSectionPlan(
                section_id=section_id,
                title=title,
                applicable=True,
                fact_ids=("fact-1",) if section_id is not PrdSectionId.DOCUMENT_INFO else (),
            )
            for section_id, title in SECTION_TITLES.items()
        ),
    )


def approval(revision: PrdRevision) -> PrdApprovalReceipt:
    return PrdApprovalReceipt(
        governance_contract_version=2,
        revision=revision.revision,
        content_hash=revision.content_hash,
        actor="owner",
        rationale="approved",
    )


def test_approved_prd_deterministically_derives_eight_authorities_and_obligations() -> None:
    revision = prd()
    first = build_design_authority(revision, approval(revision), blueprint(revision))
    second = build_design_authority(revision, approval(revision), blueprint(revision))
    obligations = extract_prd_obligations(revision, blueprint(revision))

    assert first == second
    assert tuple(item.topic for item in first.items) == AUTHORITY_TOPICS
    assert first.prd_revision == 2
    assert {item.source_prd_section_ids[0] for item in first.items} >= {
        PrdSectionId.JOURNEYS,
        PrdSectionId.RULES,
        PrdSectionId.EXCEPTIONS,
    }
    assert {item.source_fact_ids for item in first.items} == {("fact-1",)}
    assert {item.prd_section_id for item in obligations} == {
        PrdSectionId.SCOPE,
        PrdSectionId.ACTORS,
        PrdSectionId.JOURNEYS,
        PrdSectionId.RULES,
        PrdSectionId.EXCEPTIONS,
        PrdSectionId.ACCEPTANCE,
    }
    assert {item.statement for item in obligations} >= {
        "actors commitment",
        "acceptance commitment",
    }


def test_authority_derivation_rejects_unapproved_or_stale_prd() -> None:
    revision = prd()
    stale = approval(revision).model_copy(update={"revision": 1})

    with pytest.raises(ValueError, match="approved PRD revision and hash"):
        build_design_authority(revision, stale, blueprint(revision))

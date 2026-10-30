from hashlib import sha256

import pytest
from deliveryflow_contracts.prd import PrdApprovalReceipt, PrdRevision, PrdSectionId
from deliveryflow_contracts.td import (
    AUTHORITY_TOPICS,
    TD_SECTION_TITLES,
    AuthorityItem,
    DesignAuthorityPack,
    TdBlueprint,
    TdObligation,
    TdRevision,
    TdSectionId,
    TdSectionPlan,
)
from deliveryflow_speccraft.td import validate_td_obligations


def fixtures():
    content = "# 产品需求文档\n\n## 业务规则与产品边界\nOnly administrators may export.\n"
    prd = PrdRevision(
        revision=1,
        content=content,
        content_hash=sha256(content.encode()).hexdigest(),
    )
    approval = PrdApprovalReceipt(
        governance_contract_version=2,
        revision=1,
        content_hash=prd.content_hash,
        actor="owner",
        rationale="approved",
    )
    authority = DesignAuthorityPack(
        prd_revision=1,
        prd_content_hash=prd.content_hash,
        items=tuple(
            AuthorityItem(
                authority_id=f"a-{topic.value}",
                topic=topic,
                statement="Only administrators may export.",
                source_prd_section_ids=(PrdSectionId.RULES,),
            )
            for topic in AUTHORITY_TOPICS
        ),
    )
    obligation = TdObligation(
        obligation_id="o-rules",
        statement="Only administrators may export.",
        prd_section_id=PrdSectionId.RULES,
        prd_section_hash=sha256(b"Only administrators may export.").hexdigest(),
    )
    blueprint = TdBlueprint(
        prd_revision=1,
        prd_content_hash=prd.content_hash,
        authority_ids=tuple(item.authority_id for item in authority.items),
        obligation_ids=(obligation.obligation_id,),
        sections=tuple(
            TdSectionPlan(
                section_id=section_id,
                title=title,
                authority_ids=tuple(item.authority_id for item in authority.items)
                if section_id is TdSectionId.TRACEABILITY
                else (),
                obligation_ids=(obligation.obligation_id,)
                if section_id is TdSectionId.TRACEABILITY
                else (),
            )
            for section_id, title in TD_SECTION_TITLES.items()
        ),
    )
    td_content = "# TD\n\nTrace: o-rules\n"
    td = TdRevision(
        revision=1,
        content=td_content,
        content_hash=sha256(td_content.encode()).hexdigest(),
        prd_revision=1,
        prd_content_hash=prd.content_hash,
        authority_pack_hash=authority.content_hash,
        obligations=(obligation,),
    )
    return prd, approval, authority, blueprint, obligation, td


def test_td_matching_frozen_prd_obligations_is_valid() -> None:
    prd, approval, authority, blueprint, obligation, td = fixtures()

    validate_td_obligations(td, prd, approval, authority, blueprint, (obligation,))


def test_td_cannot_change_approved_permission_obligation() -> None:
    prd, approval, authority, blueprint, obligation, td = fixtures()
    changed = obligation.model_copy(update={"statement": "Every user may export."})
    changed_td = td.model_copy(update={"obligations": (changed,)})

    with pytest.raises(ValueError, match="changes a frozen PRD obligation"):
        validate_td_obligations(changed_td, prd, approval, authority, blueprint, (obligation,))


def test_td_cannot_bind_an_old_prd_hash() -> None:
    prd, approval, authority, blueprint, obligation, td = fixtures()
    stale = td.model_copy(update={"prd_content_hash": "0" * 64})

    with pytest.raises(ValueError, match="frozen PRD revision and hash"):
        validate_td_obligations(stale, prd, approval, authority, blueprint, (obligation,))

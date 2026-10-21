from hashlib import sha256

from deliveryflow_contracts.prd import PrdSectionId
from deliveryflow_contracts.td import (
    AUTHORITY_TOPICS,
    AuthorityItem,
    DesignAuthorityPack,
    TdObligation,
    TdSectionId,
)
from deliveryflow_speccraft.td import build_td_blueprint


def test_blueprint_maps_product_obligations_to_relevant_td_sections_and_traceability() -> None:
    authority = DesignAuthorityPack(
        prd_revision=1,
        prd_content_hash="a" * 64,
        items=tuple(
            AuthorityItem(
                authority_id=f"a-{topic.value}",
                topic=topic,
                statement=topic.value,
                source_prd_section_ids=(PrdSectionId.RULES,),
            )
            for topic in AUTHORITY_TOPICS
        ),
    )
    obligations = tuple(
        TdObligation(
            obligation_id=f"o-{section.value}",
            statement=section.value,
            prd_section_id=section,
            prd_section_hash=sha256(section.value.encode()).hexdigest(),
        )
        for section in PrdSectionId
        if section is not PrdSectionId.DOCUMENT_INFO
    )

    blueprint = build_td_blueprint(authority, obligations)
    plans = {section.section_id: section for section in blueprint.sections}

    assert "o-actors" in plans[TdSectionId.CONTEXT].obligation_ids
    assert "o-journeys" in plans[TdSectionId.ARCHITECTURE_FLOW].obligation_ids
    assert "o-rules" in plans[TdSectionId.API_EVENTS_ERRORS].obligation_ids
    assert "o-exceptions" in plans[TdSectionId.FAILURE_RECOVERY].obligation_ids
    assert "o-acceptance" in plans[TdSectionId.TESTING_ACCEPTANCE].obligation_ids
    assert set(plans[TdSectionId.TRACEABILITY].obligation_ids) == {
        item.obligation_id for item in obligations
    }
    assert "a-api" in plans[TdSectionId.API_EVENTS_ERRORS].authority_ids
    assert "a-idempotency" in plans[TdSectionId.CONSISTENCY].authority_ids

from hashlib import sha256

import pytest
from deliveryflow_contracts.artifacts import (
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactRef,
    DeliveryObligation,
    DeliverySpec,
)
from deliveryflow_contracts.prd import PrdSectionId
from deliveryflow_contracts.td import (
    AUTHORITY_TOPICS,
    TD_SECTION_TITLES,
    AuthorityItem,
    AuthorityTopic,
    DesignAuthorityPack,
    TdBlueprint,
    TdObligation,
    TdRevision,
    TdSectionPlan,
)
from pydantic import ValidationError

PRD_HASH = "a" * 64
TD_HASH = sha256(b"# TD\nbody\n").hexdigest()


def authority_pack() -> DesignAuthorityPack:
    return DesignAuthorityPack(
        prd_revision=2,
        prd_content_hash=PRD_HASH,
        items=tuple(
            AuthorityItem(
                authority_id=f"authority-{topic.value}",
                topic=topic,
                statement=f"approved {topic.value} obligation",
                source_fact_ids=("fact-1",),
                source_prd_section_ids=(PrdSectionId.RULES,),
            )
            for topic in AUTHORITY_TOPICS
        ),
    )


def obligation() -> TdObligation:
    return TdObligation(
        obligation_id="prd-r2-rules",
        statement="Only administrators may export.",
        prd_section_id=PrdSectionId.RULES,
        prd_section_hash="b" * 64,
        source_fact_ids=("fact-1",),
    )


def blueprint() -> TdBlueprint:
    pack = authority_pack()
    return TdBlueprint(
        prd_revision=2,
        prd_content_hash=PRD_HASH,
        authority_ids=tuple(item.authority_id for item in pack.items),
        obligation_ids=("prd-r2-rules",),
        sections=tuple(
            TdSectionPlan(
                section_id=section_id,
                title=title,
                authority_ids=tuple(item.authority_id for item in pack.items)
                if section_id.value == "traceability"
                else (),
                obligation_ids=("prd-r2-rules",)
                if section_id.value == "traceability"
                else (),
            )
            for section_id, title in TD_SECTION_TITLES.items()
        ),
    )


def test_authority_pack_requires_each_topic_exactly_once() -> None:
    valid = authority_pack()

    assert tuple(item.topic for item in valid.items) == AUTHORITY_TOPICS

    with pytest.raises(ValidationError, match="every authority topic"):
        DesignAuthorityPack(
            prd_revision=2,
            prd_content_hash=PRD_HASH,
            items=valid.items[:-1],
        )


def test_td_blueprint_must_cover_every_authority_and_obligation() -> None:
    valid = blueprint()
    assert len(valid.sections) == len(TD_SECTION_TITLES)

    with pytest.raises(ValidationError, match="cover every authority"):
        TdBlueprint.model_validate({
            **valid.model_dump(),
            "sections": [
                {**section.model_dump(), "authority_ids": ()}
                for section in valid.sections
            ],
        })


def test_td_revision_binds_exact_prd_and_content_hash() -> None:
    revision = TdRevision(
        revision=1,
        content="# TD\nbody\n",
        content_hash=TD_HASH,
        prd_revision=2,
        prd_content_hash=PRD_HASH,
        authority_pack_hash=authority_pack().content_hash,
        obligations=(obligation(),),
    )

    assert revision.content_hash == TD_HASH
    with pytest.raises(ValidationError, match="TD content hash"):
        revision.model_copy(update={"content_hash": "0" * 64}).model_dump()
        TdRevision(
            revision=1,
            content="# TD\nbody\n",
            content_hash="0" * 64,
            prd_revision=2,
            prd_content_hash=PRD_HASH,
            authority_pack_hash=authority_pack().content_hash,
            obligations=(obligation(),),
        )


def test_delivery_spec_is_machine_projection_with_refs_not_markdown_bodies() -> None:
    prd_ref = ArtifactRef(
        artifact_id="run-1:prd",
        kind=ArtifactKind.PRD,
        revision=2,
        content_hash=PRD_HASH,
        media_type="text/markdown",
    )
    td_ref = ArtifactRef(
        artifact_id="run-1:td",
        kind=ArtifactKind.TD,
        revision=1,
        content_hash=TD_HASH,
        media_type="text/markdown",
    )
    spec = DeliverySpec(
        schema_version="1.0",
        run_id="run-1",
        prd=prd_ref,
        td=td_ref,
        authority_pack_hash=authority_pack().content_hash,
        obligations=(DeliveryObligation(
            obligation_id="prd-r2-rules",
            authority_topics=(AuthorityTopic.PERMISSION,),
            td_section_ids=("traceability",),
        ),),
    )
    payload = spec.model_dump_json()
    restored = DeliverySpec.model_validate_json(payload)

    assert restored == spec
    assert "prd_content" not in payload
    assert "td_content" not in payload
    envelope = ArtifactEnvelope(
        artifact=ArtifactRef(
            artifact_id="run-1:delivery-spec",
            kind=ArtifactKind.DELIVERY_SPEC,
            revision=1,
            content_hash=sha256(payload.encode()).hexdigest(),
            media_type="application/json",
        ),
        derived_from=(prd_ref, td_ref),
    )
    assert envelope.derived_from == (prd_ref, td_ref)

import hashlib

import pytest
from deliveryflow_contracts.prd import (
    PrdApprovalRequest,
    PrdBlueprint,
    PrdRevision,
    PrdRevisionRequest,
    PrdSectionId,
    PrdSectionPlan,
)
from pydantic import ValidationError


def blueprint_sections() -> tuple[PrdSectionPlan, ...]:
    titles = (
        "文档信息",
        "背景、目标与成功标准",
        "范围与非目标",
        "角色与场景",
        "功能与核心业务流程",
        "业务规则与产品边界",
        "异常体验与产品规则",
        "验收标准",
    )
    return tuple(
        PrdSectionPlan(
            section_id=section_id,
            title=title,
            applicable=True,
            fact_ids=("fact-1",) if section_id is PrdSectionId.BACKGROUND else (),
        )
        for section_id, title in zip(PrdSectionId, titles, strict=True)
    )


def test_blueprint_covers_every_authoritative_fact_with_ordered_sections() -> None:
    blueprint = PrdBlueprint(
        ledger_revision=2,
        authoritative_fact_ids=("fact-1",),
        sections=blueprint_sections(),
    )

    assert len(blueprint.sections) == 8
    assert blueprint.sections[1].fact_ids == ("fact-1",)


def test_blueprint_rejects_missing_and_non_authoritative_fact_references() -> None:
    with pytest.raises(ValidationError, match="cover every authoritative fact"):
        PrdBlueprint(
            ledger_revision=2,
            authoritative_fact_ids=("fact-1", "fact-2"),
            sections=blueprint_sections(),
        )

    sections = list(blueprint_sections())
    sections[2] = sections[2].model_copy(update={"fact_ids": ("invented",)})
    with pytest.raises(ValidationError, match="non-authoritative fact"):
        PrdBlueprint(
            ledger_revision=2,
            authoritative_fact_ids=("fact-1",),
            sections=tuple(sections),
        )


def test_blueprint_rejects_missing_or_reordered_sections() -> None:
    with pytest.raises(ValidationError, match="template order"):
        PrdBlueprint(
            ledger_revision=2,
            authoritative_fact_ids=("fact-1",),
            sections=blueprint_sections()[::-1],
        )


def test_prd_revision_and_approval_request_bind_exact_content_hash() -> None:
    content = "# 产品需求文档\n\n## 文档信息\n内容。\n"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    revision = PrdRevision(revision=1, content=content, content_hash=content_hash)

    assert revision.content_hash == content_hash
    with pytest.raises(ValidationError, match="content hash"):
        PrdRevision(revision=1, content=content, content_hash="0" * 64)
    with pytest.raises(ValidationError):
        PrdApprovalRequest(
            governance_contract_version=2,
            revision=1,
            content_hash=content_hash,
            actor=" ",
            rationale="同意",
        )


def test_local_revision_requires_a_target_body_and_reason() -> None:
    with pytest.raises(ValidationError):
        PrdRevisionRequest(
            governance_contract_version=2,
            expected_revision=1,
            expected_content_hash="a" * 64,
            section_id=PrdSectionId.ACTORS,
            replacement_body="新的章节内容",
            feedback=" ",
        )

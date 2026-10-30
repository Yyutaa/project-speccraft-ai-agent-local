from pathlib import Path

import pytest
from deliveryflow_contracts.prd import (
    SECTION_TITLES,
    PrdBlueprint,
    PrdSectionId,
    PrdSectionPlan,
)
from deliveryflow_speccraft.model_boundary import build_prd_task
from deliveryflow_speccraft.prd_authoring import FakePrdAuthor, load_prd_authoring_pack

PACK_ROOT = Path(__file__).parent.parent / "learning-assets/authoring-pack/v1/prd"


def one_fact_blueprint() -> PrdBlueprint:
    return PrdBlueprint(
        ledger_revision=2,
        authoritative_fact_ids=("source-1",),
        sections=tuple(
            PrdSectionPlan(
                section_id=section_id,
                title=SECTION_TITLES[section_id],
                applicable=True,
                fact_ids=("source-1",) if section_id is PrdSectionId.BACKGROUND else (),
            )
            for section_id in PrdSectionId
        ),
    )


def test_authoring_pack_reads_template_guide_and_self_check() -> None:
    pack = load_prd_authoring_pack(PACK_ROOT)

    assert "## 文档信息" in pack.template
    assert "产品与技术的边界" in pack.guide
    assert "所有模板章节都已填写" in pack.self_check


def test_missing_authoring_resource_fails_explicitly(tmp_path: Path) -> None:
    (tmp_path / "template.md").write_text("# PRD", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        load_prd_authoring_pack(tmp_path)


def test_fake_author_uses_loaded_template_and_only_referenced_facts() -> None:
    pack = load_prd_authoring_pack(PACK_ROOT)
    blueprint = one_fact_blueprint()
    author = FakePrdAuthor()

    task = build_prd_task(
        blueprint,
        {"source-1": "用户可查看导出进度"},
        pack,
        evidence_refs={"source-1": ("source-evidence",)},
    )
    first = author.author(task).content
    second = author.author(task).content

    assert first == second
    assert "## 背景、目标与成功标准\n- 用户可查看导出进度" in first
    assert "{{" not in first
    assert all(f"## {title}" in first for title in SECTION_TITLES.values())


@pytest.mark.parametrize(
    "claims", [{}, {"source-1": "已确认", "reference": "支持材料"}]
)
def test_prd_author_input_rejects_missing_or_extra_claims(claims) -> None:

    with pytest.raises(ValueError, match="exactly match"):
        build_prd_task(
            one_fact_blueprint(),
            claims,
            load_prd_authoring_pack(PACK_ROOT),
            evidence_refs={key: ("source-evidence",) for key in claims},
        )

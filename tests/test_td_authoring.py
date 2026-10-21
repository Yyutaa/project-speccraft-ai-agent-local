from pathlib import Path

from deliveryflow_contracts.prd import PrdSectionId
from deliveryflow_contracts.td import (
    AUTHORITY_TOPICS,
    TD_SECTION_TITLES,
    AuthorityItem,
    DesignAuthorityPack,
    TdObligation,
)
from deliveryflow_speccraft.td import build_td_blueprint
from deliveryflow_speccraft.td_authoring import FakeTdAuthor, load_td_authoring_pack

PACK_ROOT = Path(__file__).parent.parent / "learning-assets/authoring-pack/v1/td"


def inputs():
    authority = DesignAuthorityPack(
        prd_revision=2,
        prd_content_hash="a" * 64,
        items=tuple(
            AuthorityItem(
                authority_id=f"authority-{topic.value}",
                topic=topic,
                statement=f"{topic.value} approved requirement",
                source_fact_ids=("fact-1",),
                source_prd_section_ids=(PrdSectionId.RULES,),
            )
            for topic in AUTHORITY_TOPICS
        ),
    )
    obligation = TdObligation(
        obligation_id="prd-r2-rules",
        statement="Only administrators may export.",
        prd_section_id=PrdSectionId.RULES,
        prd_section_hash="b" * 64,
        source_fact_ids=("fact-1",),
    )
    return authority, (obligation,), build_td_blueprint(authority, (obligation,))


def test_td_pack_loads_the_unified_template_guide_and_checklist() -> None:
    pack = load_td_authoring_pack(PACK_ROOT)

    assert tuple(
        line.removeprefix("## ")
        for line in pack.template.splitlines()
        if line.startswith("## ")
    ) == tuple(TD_SECTION_TITLES.values())
    assert "已批准 PRD 是产品范围事实源" in pack.guide
    assert "每项 PRD 验收标准" in pack.self_check


def test_fake_td_author_is_deterministic_and_cites_authority_obligations_and_harness() -> None:
    authority, obligations, blueprint = inputs()
    pack = load_td_authoring_pack(PACK_ROOT)
    author = FakeTdAuthor()

    first = author.author(
        blueprint,
        authority,
        obligations,
        pack,
        repository_constraints=("AGENTS.md: target repository is read-only",),
        decisions=(),
    )
    second = author.author(
        blueprint,
        authority,
        obligations,
        pack,
        repository_constraints=("AGENTS.md: target repository is read-only",),
        decisions=(),
    )

    assert first == second
    assert first.content is not None
    assert first.decision_requests == ()
    assert "PRD r2" in first.content
    assert "AGENTS.md: target repository is read-only" in first.content
    assert "prd-r2-rules" in first.content
    assert "authority-api" in first.content
    assert "{{" not in first.content
    assert all(f"## {title}" in first.content for title in TD_SECTION_TITLES.values())

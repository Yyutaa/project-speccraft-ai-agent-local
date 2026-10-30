"""Deterministic PRD blueprint and basic document checks."""

import re

from deliveryflow_contracts.facts import FactDimension, FactLedger
from deliveryflow_contracts.prd import (
    SECTION_TITLES,
    PrdBlueprint,
    PrdReadiness,
    PrdReadinessIssue,
    PrdRevision,
    PrdSectionId,
    PrdSectionPlan,
)

_DIMENSION_SECTIONS = {
    FactDimension.ROLE: PrdSectionId.ACTORS,
    FactDimension.WORKFLOW: PrdSectionId.JOURNEYS,
    FactDimension.PERMISSION: PrdSectionId.RULES,
    FactDimension.FAILURE: PrdSectionId.EXCEPTIONS,
    FactDimension.ACCEPTANCE: PrdSectionId.ACCEPTANCE,
}


def build_prd_blueprint(ledger: FactLedger) -> PrdBlueprint:
    """Map each authoritative fact to template sections without writing prose."""
    facts = ledger.authoritative_facts
    references: dict[PrdSectionId, list[str]] = {section_id: [] for section_id in PrdSectionId}
    for fact in facts:
        if fact.dimension is None:
            references[PrdSectionId.BACKGROUND].append(fact.fact_id)
        else:
            references[_DIMENSION_SECTIONS[fact.dimension]].append(fact.fact_id)
            if fact.dimension is FactDimension.WORKFLOW:
                references[PrdSectionId.SCOPE].append(fact.fact_id)
    return PrdBlueprint(
        ledger_revision=ledger.revision,
        authoritative_fact_ids=tuple(fact.fact_id for fact in facts),
        sections=tuple(
            PrdSectionPlan(
                section_id=section_id,
                title=SECTION_TITLES[section_id],
                applicable=True,
                fact_ids=tuple(references[section_id]),
            )
            for section_id in PrdSectionId
        ),
    )


_PLACEHOLDER = re.compile(r"TODO|待补充|\{\{[^}]*\}\}|<[^>]+>", re.IGNORECASE)


def check_prd_readiness(revision: PrdRevision) -> PrdReadiness:
    """Check only document structure and placeholders, never product correctness."""
    lines = revision.content.splitlines()
    headings = [
        (index, line[3:].strip())
        for index, line in enumerate(lines)
        if line.startswith("## ")
    ]
    expected = tuple(SECTION_TITLES.values())
    actual = tuple(title for _, title in headings)
    issues: list[PrdReadinessIssue] = []
    if not lines or not lines[0].startswith("# 产品需求文档"):
        issues.append(PrdReadinessIssue(code="missing_title"))
    for section_id, title in SECTION_TITLES.items():
        count = actual.count(title)
        if count == 0:
            issues.append(PrdReadinessIssue(code="missing_section", section_id=section_id))
        elif count > 1:
            issues.append(PrdReadinessIssue(code="duplicate_section", section_id=section_id))
    if any(title not in expected for title in actual):
        issues.append(PrdReadinessIssue(code="unexpected_section"))
    if len(actual) == len(expected) and actual != expected:
        issues.append(PrdReadinessIssue(code="out_of_order"))
    for position, (line_index, title) in enumerate(headings):
        matched_section_id = next(
            (candidate_id for candidate_id, expected_title in SECTION_TITLES.items()
             if expected_title == title),
            None,
        )
        if matched_section_id is None:
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_index + 1:end]).strip()
        if not body:
            issues.append(PrdReadinessIssue(code="empty_section", section_id=matched_section_id))
        elif _PLACEHOLDER.search(body):
            issues.append(PrdReadinessIssue(code="placeholder", section_id=matched_section_id))
    return PrdReadiness(
        revision=revision.revision,
        content_hash=revision.content_hash,
        issues=tuple(issues),
    )


def replace_prd_section(content: str, section_id: PrdSectionId, replacement_body: str) -> str:
    """Replace one H2 body while preserving every byte outside that section."""
    body = replacement_body.strip()
    if not body or any(line.lstrip().startswith("#") for line in body.splitlines()):
        raise ValueError("replacement must contain one body without Markdown headings")
    lines = content.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    headings = [
        (index, line[3:].strip())
        for index, line in enumerate(lines)
        if line.startswith("## ")
    ]
    matches = [position for position, (_, title) in enumerate(headings)
               if title == SECTION_TITLES[section_id]]
    if len(matches) != 1:
        raise ValueError("target PRD section is missing or duplicated")
    position = matches[0]
    start = offsets[headings[position][0] + 1]
    end = offsets[headings[position + 1][0]] if position + 1 < len(headings) else len(content)
    suffix = "\n\n" if position + 1 < len(headings) else "\n"
    return content[:start] + body + suffix + content[end:]

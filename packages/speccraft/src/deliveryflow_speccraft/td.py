"""Deterministic PRD authority, obligation, and TD blueprint construction."""

import re
from hashlib import sha256

from deliveryflow_contracts.prd import (
    PRODUCT_PRD_SECTION_IDS,
    SECTION_TITLES,
    PrdApprovalReceipt,
    PrdBlueprint,
    PrdRevision,
    PrdSectionId,
)
from deliveryflow_contracts.td import (
    AUTHORITY_TOPICS,
    TD_SECTION_TITLES,
    AuthorityItem,
    AuthorityTopic,
    DesignAuthorityPack,
    TdBlueprint,
    TdObligation,
    TdReadiness,
    TdReadinessIssue,
    TdRevision,
    TdSectionId,
    TdSectionPlan,
)

_AUTHORITY_SOURCE = {
    AuthorityTopic.API: PrdSectionId.JOURNEYS,
    AuthorityTopic.DATA: PrdSectionId.SCOPE,
    AuthorityTopic.ERROR: PrdSectionId.EXCEPTIONS,
    AuthorityTopic.IDEMPOTENCY: PrdSectionId.RULES,
    AuthorityTopic.PERMISSION: PrdSectionId.RULES,
    AuthorityTopic.STATE: PrdSectionId.JOURNEYS,
    AuthorityTopic.FAILURE: PrdSectionId.EXCEPTIONS,
    AuthorityTopic.NON_FUNCTIONAL: PrdSectionId.SCOPE,
}

_AUTHORITY_SECTION = {
    AuthorityTopic.API: TdSectionId.API_EVENTS_ERRORS,
    AuthorityTopic.DATA: TdSectionId.DOMAIN_DATA_STATE,
    AuthorityTopic.ERROR: TdSectionId.API_EVENTS_ERRORS,
    AuthorityTopic.IDEMPOTENCY: TdSectionId.CONSISTENCY,
    AuthorityTopic.PERMISSION: TdSectionId.PERFORMANCE_SECURITY_OBSERVABILITY,
    AuthorityTopic.STATE: TdSectionId.DOMAIN_DATA_STATE,
    AuthorityTopic.FAILURE: TdSectionId.FAILURE_RECOVERY,
    AuthorityTopic.NON_FUNCTIONAL: TdSectionId.PERFORMANCE_SECURITY_OBSERVABILITY,
}

_OBLIGATION_SECTION = {
    PrdSectionId.SCOPE: TdSectionId.CHANGE_SCOPE,
    PrdSectionId.ACTORS: TdSectionId.CONTEXT,
    PrdSectionId.JOURNEYS: TdSectionId.ARCHITECTURE_FLOW,
    PrdSectionId.RULES: TdSectionId.API_EVENTS_ERRORS,
    PrdSectionId.EXCEPTIONS: TdSectionId.FAILURE_RECOVERY,
    PrdSectionId.ACCEPTANCE: TdSectionId.TESTING_ACCEPTANCE,
}


def _section_bodies(content: str) -> dict[PrdSectionId, str]:
    lines = content.splitlines()
    headings = [
        (index, section_id)
        for index, line in enumerate(lines)
        for section_id, title in SECTION_TITLES.items()
        if line == f"## {title}"
    ]
    bodies: dict[PrdSectionId, str] = {}
    for position, (start, section_id) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        bodies[section_id] = "\n".join(lines[start + 1:end]).strip()
    if set(bodies) != set(PrdSectionId):
        raise ValueError("approved PRD must contain every canonical section exactly once")
    return bodies


def _assert_approved(prd: PrdRevision, approval: PrdApprovalReceipt) -> None:
    if approval.revision != prd.revision or approval.content_hash != prd.content_hash:
        raise ValueError("approved PRD revision and hash must match the current PRD")


def build_design_authority(
    prd: PrdRevision,
    approval: PrdApprovalReceipt,
    blueprint: PrdBlueprint,
) -> DesignAuthorityPack:
    """Derive eight technical authority inputs from one frozen PRD."""
    _assert_approved(prd, approval)
    bodies = _section_bodies(prd.content)
    plans = {section.section_id: section for section in blueprint.sections}
    return DesignAuthorityPack(
        prd_revision=prd.revision,
        prd_content_hash=prd.content_hash,
        items=tuple(
            AuthorityItem(
                authority_id=f"prd-r{prd.revision}-{topic.value}",
                topic=topic,
                statement=bodies[_AUTHORITY_SOURCE[topic]],
                source_fact_ids=plans[_AUTHORITY_SOURCE[topic]].fact_ids,
                source_prd_section_ids=(_AUTHORITY_SOURCE[topic],),
            )
            for topic in AUTHORITY_TOPICS
        ),
    )


def extract_prd_obligations(
    prd: PrdRevision, blueprint: PrdBlueprint
) -> tuple[TdObligation, ...]:
    """Freeze each product section body as a traceable technical obligation."""
    bodies = _section_bodies(prd.content)
    plans = {section.section_id: section for section in blueprint.sections}
    return tuple(
        TdObligation(
            obligation_id=f"prd-r{prd.revision}-{section_id.value}",
            statement=bodies[section_id],
            prd_section_id=section_id,
            prd_section_hash=sha256(bodies[section_id].encode()).hexdigest(),
            source_fact_ids=plans[section_id].fact_ids,
        )
        for section_id in PRODUCT_PRD_SECTION_IDS
    )


def build_td_blueprint(
    authority: DesignAuthorityPack, obligations: tuple[TdObligation, ...]
) -> TdBlueprint:
    """Map every authority and PRD obligation into the unified TD template."""
    authority_by_section: dict[TdSectionId, list[str]] = {
        section_id: [] for section_id in TdSectionId
    }
    for item in authority.items:
        authority_by_section[_AUTHORITY_SECTION[item.topic]].append(item.authority_id)
    obligations_by_section: dict[TdSectionId, list[str]] = {
        section_id: [] for section_id in TdSectionId
    }
    for obligation in obligations:
        obligations_by_section[_OBLIGATION_SECTION[obligation.prd_section_id]].append(
            obligation.obligation_id
        )
        obligations_by_section[TdSectionId.TRACEABILITY].append(obligation.obligation_id)
    return TdBlueprint(
        prd_revision=authority.prd_revision,
        prd_content_hash=authority.prd_content_hash,
        authority_ids=tuple(item.authority_id for item in authority.items),
        obligation_ids=tuple(item.obligation_id for item in obligations),
        sections=tuple(
            TdSectionPlan(
                section_id=section_id,
                title=title,
                authority_ids=tuple(authority_by_section[section_id]),
                obligation_ids=tuple(obligations_by_section[section_id]),
            )
            for section_id, title in TD_SECTION_TITLES.items()
        ),
    )


def validate_td_obligations(
    td: TdRevision,
    prd: PrdRevision,
    approval: PrdApprovalReceipt,
    authority: DesignAuthorityPack,
    blueprint: TdBlueprint,
    obligations: tuple[TdObligation, ...],
) -> None:
    """Reject stale or structurally altered product commitments before approval."""
    _assert_approved(prd, approval)
    if td.prd_revision != prd.revision or td.prd_content_hash != prd.content_hash:
        raise ValueError("TD must bind the frozen PRD revision and hash")
    if (
        authority.prd_revision != prd.revision
        or authority.prd_content_hash != prd.content_hash
        or td.authority_pack_hash != authority.content_hash
        or blueprint.prd_revision != prd.revision
        or blueprint.prd_content_hash != prd.content_hash
    ):
        raise ValueError("TD authority and Blueprint must bind the frozen PRD")
    if td.obligations != obligations:
        raise ValueError("TD changes a frozen PRD obligation")
    if set(blueprint.obligation_ids) != {item.obligation_id for item in obligations}:
        raise ValueError("TD Blueprint does not cover the frozen PRD obligations")
    if any(item.obligation_id not in td.content for item in obligations):
        raise ValueError("TD content must cite every frozen PRD obligation")


_PLACEHOLDER = re.compile(r"TODO|待补充|\{\{[^}]*\}\}|<[^>]+>", re.IGNORECASE)


def check_td_readiness(revision: TdRevision) -> TdReadiness:
    """Check only document structure and placeholders, never product correctness."""
    lines = revision.content.splitlines()
    headings = [
        (index, line[3:].strip())
        for index, line in enumerate(lines)
        if line.startswith("## ")
    ]
    expected = tuple(TD_SECTION_TITLES.values())
    actual = tuple(title for _, title in headings)
    issues: list[TdReadinessIssue] = []
    if not lines or not lines[0].startswith("# 统一技术设计（TD）"):
        issues.append(TdReadinessIssue(code="missing_title"))
    for section_id, title in TD_SECTION_TITLES.items():
        count = actual.count(title)
        if count == 0:
            issues.append(TdReadinessIssue(code="missing_section", section_id=section_id))
        elif count > 1:
            issues.append(TdReadinessIssue(code="duplicate_section", section_id=section_id))
    if any(title not in expected for title in actual):
        issues.append(TdReadinessIssue(code="unexpected_section"))
    if len(actual) == len(expected) and actual != expected:
        issues.append(TdReadinessIssue(code="out_of_order"))
    for position, (line_index, title) in enumerate(headings):
        matched_section_id = next(
            (candidate_id for candidate_id, expected_title in TD_SECTION_TITLES.items()
             if expected_title == title),
            None,
        )
        if matched_section_id is None:
            continue
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_index + 1:end]).strip()
        if not body:
            issues.append(TdReadinessIssue(code="empty_section", section_id=matched_section_id))
        elif _PLACEHOLDER.search(body):
            issues.append(TdReadinessIssue(code="placeholder", section_id=matched_section_id))
    return TdReadiness(
        revision=revision.revision,
        content_hash=revision.content_hash,
        issues=tuple(issues), ready=not issues,
    )


def replace_td_section(content: str, section_id: TdSectionId, replacement_body: str) -> str:
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
               if title == TD_SECTION_TITLES[section_id]]
    if len(matches) != 1:
        raise ValueError("target PRD section is missing or duplicated")
    position = matches[0]
    start = offsets[headings[position][0] + 1]
    end = offsets[headings[position + 1][0]] if position + 1 < len(headings) else len(content)
    suffix = "\n\n" if position + 1 < len(headings) else "\n"
    return content[:start] + body + suffix + content[end:]

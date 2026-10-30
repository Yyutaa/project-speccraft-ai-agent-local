"""Deterministic evidence checks for explicit human TD reviews, without semantic inference."""

from uuid import uuid4

from deliveryflow_contracts.runs import RunResponse
from deliveryflow_contracts.td import (
    RecordTdReviewRequest,
    TdReviewBinding,
    TdReviewFinding,
    TdReviewProjection,
    TdReviewRecord,
    td_obligations_hash,
    td_review_conclusion,
)

from deliveryflow_speccraft.td import (
    check_td_readiness,
    extract_prd_obligations,
    validate_td_obligations,
)


def current_td_review_binding(run: RunResponse) -> TdReviewBinding:
    if (
        run.prd_draft is None
        or run.prd_approval is None
        or run.td_draft is None
        or run.design_authority is None
        or run.prd_approval.revision != run.prd_draft.revision
        or run.prd_approval.content_hash != run.prd_draft.content_hash
    ):
        raise ValueError("review requires the current approved PRD and TD")
    return TdReviewBinding(
        run_id=run.run_id,
        prd_revision=run.prd_draft.revision,
        prd_content_hash=run.prd_draft.content_hash,
        td_revision=run.td_draft.revision,
        td_content_hash=run.td_draft.content_hash,
        authority_pack_hash=run.design_authority.content_hash,
        obligations_hash=td_obligations_hash(run.td_draft.obligations),
    )


def record_td_review(run: RunResponse, request: RecordTdReviewRequest) -> TdReviewRecord:
    """Validate an explicitly confirmed report and retain all existing finding evidence."""
    assert run.td_draft is not None and run.prd_draft is not None
    assert run.prd_approval is not None and run.design_authority is not None
    assert run.prd_blueprint is not None and run.td_blueprint is not None
    expected = {item.obligation_id for item in run.td_draft.obligations}
    if set(request.reviewed_obligation_ids) != expected or len(
        request.reviewed_obligation_ids
    ) != len(expected):
        raise ValueError("review must cover every frozen obligation exactly once")
    previous = run.td_review_records[-1] if run.td_review_records else None
    if request.prior_review_id != (previous.review_id if previous else None):
        raise ValueError("review must reference the previous report")
    existing = {item.finding_id: item for item in previous.findings} if previous else {}
    dispositions = {item.finding_id: item for item in request.existing_finding_dispositions}
    unresolved = {key for key, item in existing.items() if item.disposition != "dismissed"}
    rechecks = {item.finding_id: item for item in request.rechecks}
    new_revision = (
        previous is not None and previous.binding.td_revision < request.binding.td_revision
    )
    if len(dispositions) != len(request.existing_finding_dispositions) or set(dispositions) - set(
        existing
    ):
        raise ValueError("dispositions require unique existing findings")
    if new_revision:
        if (
            len(rechecks) != len(request.rechecks)
            or set(rechecks) != unresolved
            or set(dispositions) & unresolved
        ):
            raise ValueError("new TD review must recheck every unresolved finding exactly once")
    elif rechecks or not unresolved <= set(dispositions):
        raise ValueError("same TD review requires dispositions and cannot claim a fix")
    findings: list[TdReviewFinding] = []
    for key, item in existing.items():
        change = dispositions[key].model_dump() if key in dispositions else {}
        if key in rechecks:
            recheck = rechecks[key]
            if recheck.outcome == "still_present":
                excerpt = recheck.td_excerpt
                if (
                    excerpt is None
                    or run.td_draft.content[excerpt.start : excerpt.end] != excerpt.excerpt
                ):
                    raise ValueError("still_present requires an exact current TD excerpt")
            else:
                if (
                    recheck.outcome == "fixed"
                    and previous is not None
                    and previous.binding.td_content_hash == request.binding.td_content_hash
                ):
                    raise ValueError("fixed requires changed content in a new TD revision")
                if recheck.td_excerpt is not None and (
                    run.td_draft.content[recheck.td_excerpt.start : recheck.td_excerpt.end]
                    != recheck.td_excerpt.excerpt
                ):
                    raise ValueError("recheck excerpt must match the current TD")
                change = {"disposition": "dismissed", "disposition_rationale": recheck.rationale}
        findings.append(TdReviewFinding.model_validate(item.model_dump() | change))
    new_ids = [item.finding_id for item in request.findings]
    if len(new_ids) != len(set(new_ids)) or set(new_ids) & set(existing):
        raise ValueError("new finding IDs must be unique and cannot replace history")
    findings.extend(request.findings)
    for item in request.findings:
        if not set(item.obligation_ids) <= expected or len(set(item.obligation_ids)) != len(
            item.obligation_ids
        ):
            raise ValueError("finding must cite known frozen obligations exactly once")
        for excerpt, content in (
            (item.prd_excerpt, run.prd_draft.content),
            (item.td_excerpt, run.td_draft.content),
        ):
            if content[excerpt.start : excerpt.end] != excerpt.excerpt:
                raise ValueError("finding excerpt must match the exact document interval")
    blockers = [item for item in findings if item.disposition != "dismissed"]
    conclusion = td_review_conclusion(tuple(findings))
    if request.human_conclusion != conclusion:
        raise ValueError("human conclusion must agree with explicit finding dispositions")
    structure_ready = check_td_readiness(run.td_draft).ready
    try:
        validate_td_obligations(
            run.td_draft,
            run.prd_draft,
            run.prd_approval,
            run.design_authority,
            run.td_blueprint,
            extract_prd_obligations(run.prd_draft, run.prd_blueprint),
        )
    except ValueError:
        structure_ready = False
    return TdReviewRecord(
        review_id=str(uuid4()),
        review_revision=request.expected_review_revision + 1,
        command_id=request.command_id,
        binding=request.binding,
        actor_claim=request.actor_claim,
        rationale=request.rationale,
        human_conclusion=request.human_conclusion,
        reviewed_obligation_ids=request.reviewed_obligation_ids,
        findings=tuple(findings),
        prior_review_id=request.prior_review_id,
        rechecks=request.rechecks,
        computed_status="ready" if structure_ready and not blockers else "blocked",
    )


def td_review_projection(binding: TdReviewBinding, record: TdReviewRecord) -> TdReviewProjection:
    return TdReviewProjection(
        binding=binding,
        status=record.computed_status,
        current_review_id=record.review_id,
        review_revision=record.review_revision,
        blocking_finding_ids=tuple(
            item.finding_id for item in record.findings if item.disposition != "dismissed"
        ),
    )

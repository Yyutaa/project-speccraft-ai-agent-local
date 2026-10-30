"""Pure admission of exact user-confirmed excerpts; no Runner state or file reads."""

from hashlib import sha256
from uuid import uuid4

from deliveryflow_contracts.context import SourceSnapshot
from deliveryflow_contracts.facts import FactKind, RequirementFact, SourceEvidence
from deliveryflow_contracts.sources import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATES,
    AdmissionModel,
    PendingSourceClaim,
    RunSources,
    SourceAdmissionCommand,
    SourceAdmissionEvidence,
    SourceClaimAction,
    SourceClaimReview,
    SourceClaimStatus,
    SourceRecord,
    source_role_for_snapshot,
    validate_source_claim_binding,
)


class SourceAdmissionResult(AdmissionModel):
    candidate: PendingSourceClaim
    evidence: SourceAdmissionEvidence
    fact: RequirementFact | None


def make_source_record(
    run_id: str, snapshot: SourceSnapshot, repository_id: str | None = None,
) -> SourceRecord:
    """Wrap a server-captured snapshot; file callers must use RepositoryHarness first."""
    captured = SourceSnapshot.model_validate(snapshot.model_dump())
    return SourceRecord(
        source_id=str(uuid4()), run_id=run_id, repository_id=repository_id,
        source_role=source_role_for_snapshot(captured), snapshot=captured,
    )


def build_source_candidates(
    source: SourceRecord, ranges: tuple[tuple[int, int], ...] = (),
) -> tuple[PendingSourceClaim, ...]:
    """Build unclassified proposals, enforcing code-point ranges and a UTF-8 budget."""
    source = SourceRecord.model_validate(source.model_dump())
    if not source.source_role.permits_product_claim:
        # Candidates are product-admission objects, not a knowledge or Harness channel.
        raise ValueError("only a product requirement source may supply a source claim")
    selected = ranges or ((0, len(source.snapshot.content)),)
    if len(selected) != len(set(selected)):
        raise ValueError("source candidate intervals must be unique")
    if len(selected) > MAX_CANDIDATES:
        raise ValueError("at most 32 candidate intervals are allowed")
    candidates = tuple(
        PendingSourceClaim(
            candidate_id=f"{source.source_id}:{index}", source_id=source.source_id,
            source_sha256=source.snapshot.sha256, start=start, end=end,
            excerpt=source.snapshot.content[start:end], candidate_revision=1,
        )
        for index, (start, end) in enumerate(selected, start=1)
    )
    if sum(len(item.excerpt.encode("utf-8")) for item in candidates) > MAX_CANDIDATE_BYTES:
        raise ValueError("total candidate excerpts exceed 64 KiB UTF-8")
    return candidates


def admit_source_claim(
    run_sources: RunSources, candidate: PendingSourceClaim,
    review: SourceClaimReview, command: SourceAdmissionCommand,
) -> SourceAdmissionResult:
    """Validate exact evidence and return a proposal to commit, without changing input.

    The caller supplies the current stored candidate and owns command replay, batch and
    Ledger revision checks. A claimed actor identifies submitted text, not authentication.
    """
    run_sources = RunSources.model_validate(run_sources.model_dump())
    candidate = PendingSourceClaim.model_validate(candidate.model_dump())
    review = SourceClaimReview.model_validate(review.model_dump())
    command = SourceAdmissionCommand.model_validate(command.model_dump())
    if command.run_id != run_sources.run_id:
        raise ValueError("confirmation command must belong to this Run")
    source = next((item for item in run_sources.records
                   if item.source_id == candidate.source_id), None)
    if source is None:
        raise ValueError("candidate source must belong to this Run")
    if not source.source_role.permits_product_claim:
        raise ValueError("only a product requirement source may supply a source claim")
    if candidate.status is not SourceClaimStatus.PENDING or (
        review.candidate_id != candidate.candidate_id
        or review.candidate_revision != candidate.candidate_revision
    ):
        raise ValueError("review requires the current unprocessed candidate revision")
    if review.source_id != candidate.source_id or review.source_sha256 != candidate.source_sha256:
        raise ValueError("review must bind the candidate's own source identity and SHA-256")
    validate_source_claim_binding(run_sources, candidate)
    evidence = SourceAdmissionEvidence(
        **command.model_dump(), **review.model_dump(),
        start=candidate.start, end=candidate.end, excerpt=candidate.excerpt,
    )
    accepted = review.action is SourceClaimAction.ACCEPT
    processed = PendingSourceClaim.model_validate({
        **candidate.model_dump(),
        "status": SourceClaimStatus.ACCEPTED if accepted else SourceClaimStatus.REJECTED,
    })
    fact = None
    if accepted:
        identity = f"{command.run_id}:{command.command_id}:{candidate.candidate_id}"
        fact = RequirementFact(
            fact_id=f"source-fact-{sha256(identity.encode()).hexdigest()}", kind=FactKind.FACT,
            dimension=review.dimension, claim=candidate.excerpt.strip(),
            source=SourceEvidence(sha256=candidate.source_sha256, excerpt=candidate.excerpt),
            source_id=candidate.source_id, admission_evidence=evidence,
        )
    return SourceAdmissionResult(candidate=processed, evidence=evidence, fact=fact)

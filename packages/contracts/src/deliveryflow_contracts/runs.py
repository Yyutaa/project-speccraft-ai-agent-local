"""Public request and response models for the in-memory Run demonstration."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.artifacts import ArtifactEnvelope, ArtifactKind, DeliverySpec
from deliveryflow_contracts.context import (
    ContextMode,
    HarnessContextSlice,
    RepositoryBinding,
    SourceSnapshot,
)
from deliveryflow_contracts.facts import (
    ClarificationBatch,
    CompletenessResult,
    FactKind,
    FactLedger,
    RequirementFact,
)
from deliveryflow_contracts.governance import GovernanceWriteRequest
from deliveryflow_contracts.knowledge import (
    Assumption,
    AssumptionInput,
    AssumptionResolutionEvidence,
    ContextConflict,
    ContextConflictInput,
    ContextReference,
    ContextResolutionEvidence,
    KnowledgeCitation,
    KnowledgeSelection,
    RuleMetadata,
)
from deliveryflow_contracts.prd import (
    PrdApprovalReceipt,
    PrdBlueprint,
    PrdReadiness,
    PrdRevision,
    PrdSupportingContext,
)
from deliveryflow_contracts.sources import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATES,
    PendingSourceClaim,
    RunSources,
    SourceAdmissionEvidence,
    SourceClaimAction,
    SourceClaimStatus,
    SourceRecord,
    source_role_for_snapshot,
    validate_source_claim_binding,
)
from deliveryflow_contracts.td import (
    DesignAuthorityPack,
    TdApprovalReceipt,
    TdBlueprint,
    TdReadiness,
    TdReviewBinding,
    TdReviewProjection,
    TdReviewRecord,
    TdRevision,
    TechnicalDecision,
    TechnicalDecisionRequest,
    td_obligations_hash,
)


class RunStatus(StrEnum):
    AWAITING_CLARIFICATION = "awaiting_clarification"
    PRD_AWAITING_APPROVAL = "prd_awaiting_approval"
    TD_AWAITING_DECISION = "td_awaiting_decision"
    TD_AWAITING_APPROVAL = "td_awaiting_approval"
    COMPLETED = "completed"


class AvailableCommand(StrEnum):
    SUBMIT_CLARIFICATION = "submit_clarification"
    REVISE_PRD = "revise_prd"
    APPROVE_PRD = "approve_prd"
    SUBMIT_TECHNICAL_DECISIONS = "submit_technical_decisions"
    RECORD_TD_REVIEW = "record_td_review"
    REVISE_TD = "revise_td"
    APPROVE_TD = "approve_td"


class ClaimSelection(RuleMetadata):
    model_config = ConfigDict(frozen=True, extra="forbid")

    client_ref: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def validate_interval(self) -> "ClaimSelection":
        if self.start >= self.end:
            raise ValueError("selection must be a nonempty interval")
        return self


class CreateRunRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_selections: tuple[ClaimSelection, ...] = Field(
        default=(),
        max_length=32,
        description=(
            "Explicit candidates; omitted selection creates alias requirement_candidate. "
            "The source alias is requirement_source."
        ),
    )
    knowledge_selections: tuple[KnowledgeSelection, ...] = Field(default=(), max_length=8)
    assumptions: tuple[AssumptionInput, ...] = Field(default=(), max_length=32)
    context_conflicts: tuple[ContextConflictInput, ...] = Field(default=(), max_length=32)
    parent_run_id: str | None = Field(default=None, min_length=1, pattern=r"(?s).*\S.*")
    requirement: str | None = None
    requirement_path: str | None = Field(default=None, min_length=1)
    context_mode: ContextMode = ContextMode.INDEXED_READONLY

    @model_validator(mode="after")
    def require_one_requirement_source(self) -> "CreateRunRequest":
        refs = (
            [item.client_ref for item in self.claim_selections]
            + [item.client_ref for item in self.knowledge_selections]
            + [item.client_ref for item in self.assumptions]
            + [item.client_ref for item in self.context_conflicts]
        )
        refs.extend(["requirement_source", "requirement_candidate"])
        if len(refs) != len(set(refs)):
            raise ValueError("claim selection client refs must be unique")
        intervals = [(item.start, item.end) for item in self.claim_selections]
        if len(intervals) != len(set(intervals)):
            raise ValueError("source candidate intervals must be unique")
        has_inline = self.requirement is not None and bool(self.requirement.strip())
        has_file = self.requirement_path is not None and bool(self.requirement_path.strip())
        if has_inline == has_file:
            raise ValueError("provide exactly one nonblank requirement or requirement_path")
        return self


class RunResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    governance_contract_version: Literal[2] = 2
    run_id: str = Field(min_length=1)
    parent_run_id: str | None = Field(default=None, min_length=1)
    requirement: str = Field(min_length=1)
    status: RunStatus
    prd_blueprint: PrdBlueprint | None = None
    prd_revisions: tuple[PrdRevision, ...] = ()
    prd_draft: PrdRevision | None = None
    prd_readiness: PrdReadiness | None = None
    prd_approval: PrdApprovalReceipt | None = None
    prd_supporting_context: PrdSupportingContext = Field(default_factory=PrdSupportingContext)
    design_authority: DesignAuthorityPack | None = None
    td_blueprint: TdBlueprint | None = None
    technical_decision_requests: tuple[TechnicalDecisionRequest, ...] = ()
    technical_decisions: tuple[TechnicalDecision, ...] = ()
    td_draft: TdRevision | None = None
    td_revisions: tuple[TdRevision, ...] = ()
    td_readiness: TdReadiness | None = None
    td_approval: TdApprovalReceipt | None = None
    td_review: TdReviewProjection | None = None
    td_review_records: tuple[TdReviewRecord, ...] = ()
    delivery_spec: DeliverySpec | None = None
    artifact_envelopes: tuple[ArtifactEnvelope, ...] = ()
    available_commands: tuple[AvailableCommand, ...]
    source_snapshot: SourceSnapshot
    repository_binding: RepositoryBinding
    harness_context: HarnessContextSlice
    ledger: FactLedger
    completeness: CompletenessResult
    clarification_batch: ClarificationBatch | None = None
    source_records: tuple[SourceRecord, ...]
    pending_source_claims: tuple[PendingSourceClaim, ...]
    source_admission_evidence: tuple[SourceAdmissionEvidence, ...] = ()

    knowledge_citations: tuple[KnowledgeCitation, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    context_conflicts: tuple[ContextConflict, ...] = ()
    assumption_resolution_evidence: tuple[AssumptionResolutionEvidence, ...] = ()
    context_resolution_evidence: tuple[ContextResolutionEvidence, ...] = ()

    def _validate_admission_projection(self) -> None:
        sources = RunSources(run_id=self.run_id, records=self.source_records)
        captured = (
            self.source_snapshot,
            *(entry.snapshot for entry in self.harness_context.entries),
            *(
                record.snapshot
                for record in self.source_records
                if record.source_role.value == "business_knowledge"
            ),
        )
        if self.requirement != self.source_snapshot.content.strip():
            raise ValueError("Run requirement must match its captured requirement snapshot")
        expected_records = {(item.normalized_path, item.sha256): item for item in captured}
        if len(sources.records) != len(expected_records):
            raise ValueError("source registry must cover exactly the captured snapshots")
        for record in sources.records:
            snapshot = expected_records.get(
                (record.snapshot.normalized_path, record.snapshot.sha256)
            )
            if (
                snapshot is None
                or record.snapshot != snapshot
                or (
                    record.repository_id
                    != (
                        self.repository_binding.repository_id
                        if snapshot.normalized_path is not None
                        else None
                    )
                )
                or record.source_role is not source_role_for_snapshot(snapshot)
            ):
                raise ValueError("source registry must bind the Run's captured snapshot and role")
        requirement_record = next(
            (record for record in sources.records if record.snapshot == self.source_snapshot), None
        )
        if requirement_record is None or not requirement_record.source_role.permits_product_claim:
            raise ValueError("captured requirement must use a product requirement role")
        candidates = tuple(
            PendingSourceClaim.model_validate(candidate.model_dump())
            for candidate in self.pending_source_claims
        )
        intervals = [(item.source_id, item.start, item.end) for item in candidates]
        if len(intervals) != len(set(intervals)):
            raise ValueError("source candidate intervals must be unique")
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)) or len(candidates) > MAX_CANDIDATES:
            raise ValueError("source candidates must have unique IDs and number at most 32")
        if sum(len(candidate.excerpt.encode("utf-8")) for candidate in candidates) > (
            MAX_CANDIDATE_BYTES
        ):
            raise ValueError("Run candidate excerpts exceed 64 KiB UTF-8")
        for candidate in candidates:
            validate_source_claim_binding(sources, candidate)
        evidence_by_candidate: dict[str, SourceAdmissionEvidence] = {}
        review_ids = set()
        for original_evidence in self.source_admission_evidence:
            evidence = SourceAdmissionEvidence.model_validate(original_evidence.model_dump())
            if evidence.candidate_id in evidence_by_candidate or evidence.review_id in review_ids:
                raise ValueError("each candidate has one unique admission review")
            evidence_by_candidate[evidence.candidate_id] = evidence
            review_ids.add(evidence.review_id)
        for candidate in candidates:
            candidate_evidence = evidence_by_candidate.get(candidate.candidate_id)
            if candidate.status is SourceClaimStatus.PENDING:
                if candidate_evidence is not None:
                    raise ValueError("pending candidates cannot have admission evidence")
            elif candidate_evidence is None or (
                candidate_evidence.run_id != self.run_id
                or candidate_evidence.candidate_revision != candidate.candidate_revision
                or candidate_evidence.source_id != candidate.source_id
                or candidate_evidence.source_sha256 != candidate.source_sha256
                or candidate_evidence.start != candidate.start
                or candidate_evidence.end != candidate.end
                or candidate_evidence.excerpt != candidate.excerpt
                or (candidate_evidence.action is SourceClaimAction.ACCEPT)
                != (candidate.status is SourceClaimStatus.ACCEPTED)
                or candidate_evidence.expected_revision >= self.ledger.revision
            ):
                raise ValueError("processed candidate must bind its stored admission evidence")
        if set(evidence_by_candidate) - set(candidate_ids):
            raise ValueError("admission evidence requires a captured candidate")
        admitted_candidate_versions: set[tuple[str, int]] = set()
        for fact in self.ledger.facts:
            if fact.kind is FactKind.FACT and fact.admission_evidence is not None:
                key = (
                    fact.admission_evidence.candidate_id,
                    fact.admission_evidence.candidate_revision,
                )
                if key in admitted_candidate_versions:
                    raise ValueError("a source candidate version can produce only one FACT")
                admitted_candidate_versions.add(key)
        for original in self.ledger.facts:
            fact = RequirementFact.model_validate(original.model_dump())
            if fact.kind is not FactKind.FACT:
                continue
            fact_evidence = fact.admission_evidence
            if (
                fact_evidence is None
                or fact_evidence.run_id != self.run_id
                or evidence_by_candidate.get(fact_evidence.candidate_id) != fact_evidence
            ):
                raise ValueError("new source projection requires precise FACT admission evidence")
            accepted_candidate = next(
                (item for item in candidates if item.candidate_id == fact_evidence.candidate_id),
                None,
            )
            if accepted_candidate is None or (
                accepted_candidate.status is not SourceClaimStatus.ACCEPTED
                or accepted_candidate.candidate_revision != fact_evidence.candidate_revision
                or accepted_candidate.source_id != fact_evidence.source_id
                or accepted_candidate.source_sha256 != fact_evidence.source_sha256
                or accepted_candidate.start != fact_evidence.start
                or accepted_candidate.end != fact_evidence.end
                or accepted_candidate.excerpt != fact_evidence.excerpt
            ):
                raise ValueError("FACT admission must bind its current accepted source candidate")
        accepted_versions = {
            (item.candidate_id, item.candidate_revision)
            for item in candidates
            if item.status is SourceClaimStatus.ACCEPTED
        }
        if admitted_candidate_versions != accepted_versions:
            raise ValueError("every accepted candidate must have exactly one admitted FACT")

    def _validate_governance_projection(self) -> None:
        records = {item.source_id: item for item in self.source_records}
        candidates = {item.candidate_id: item for item in self.pending_source_claims}
        citations = {item.citation_id: item for item in self.knowledge_citations}
        assumptions = {item.assumption_id: item for item in self.assumptions}
        conflicts = {item.conflict_id: item for item in self.context_conflicts}
        facts = {item.fact_id: item for item in self.ledger.facts}
        for values, items in (
            (citations, self.knowledge_citations),
            (assumptions, self.assumptions),
            (conflicts, self.context_conflicts),
        ):
            if len(values) != len(items):
                raise ValueError("governance object IDs must be unique")
        if (
            len(citations) > 8
            or sum(len(c.excerpt.encode("utf-8")) for c in citations.values()) > 16384
        ):
            raise ValueError("knowledge citations exceed the finite reference budget")
        for citation in self.knowledge_citations:
            citation = KnowledgeCitation.model_validate(citation.model_dump())
            record = records.get(citation.source_id)
            if (
                record is None
                or record.source_role.value != "business_knowledge"
                or record.snapshot.sha256 != citation.source_sha256
                or record.snapshot.content[citation.start : citation.end] != citation.excerpt
                or not set(citation.related_candidate_ids).issubset(candidates)
                or not set(citation.related_assumption_ids).issubset(assumptions)
                or not set(citation.related_fact_ids).issubset(facts)
            ):
                raise ValueError(
                    "knowledge citation must bind this Run's exact business source and links"
                )
            expected_fact_ids = tuple(
                f.fact_id
                for key in citation.related_candidate_ids
                for f in self.ledger.facts
                if f.admission_evidence is not None and f.admission_evidence.candidate_id == key
            )
            if citation.related_fact_ids != expected_fact_ids:
                raise ValueError(
                    "citation fact links must resolve the actual admitted candidate mapping"
                )

        def validate_reference(reference: ContextReference) -> None:
            ref = ContextReference.model_validate(reference.model_dump())
            record = records.get(ref.source_id)
            if (
                record is None
                or record.source_role.value in ("repository_guide", "repository_metadata")
                or record.snapshot.sha256 != ref.source_sha256
                or record.snapshot.content[ref.start : ref.end] != ref.excerpt
            ):
                raise ValueError(
                    "context reference requires an exact captured non-engineering source interval"
                )
            if ref.kind == "source":
                if ref.reference_id != ref.source_id:
                    raise ValueError("source reference identity must match its captured source")
                return
            target = (
                candidates.get(ref.reference_id)
                if ref.kind == "candidate"
                else citations.get(ref.reference_id)
            )
            if target is None or any(
                getattr(target, key) != getattr(ref, key)
                for key in ("source_id", "source_sha256", "start", "end", "excerpt")
            ):
                raise ValueError("context reference must bind this Run's candidate or citation")

        assumption_evidence = {
            item.assumption_id: item for item in self.assumption_resolution_evidence
        }
        conflict_evidence = {item.conflict_id: item for item in self.context_resolution_evidence}
        if len(assumption_evidence) != len(self.assumption_resolution_evidence) or len(
            conflict_evidence
        ) != len(self.context_resolution_evidence):
            raise ValueError("each governance object version has one resolution")
        required_gaps = {}
        for original in self.assumptions:
            item = Assumption.model_validate(original.model_dump())
            for ref in item.basis_refs:
                validate_reference(ref)
            if item.blocking:
                required_gaps[f"assumption-{item.assumption_id}"] = (
                    "assumption",
                    item.assumption_id,
                    item.revision,
                )
            if item.supersedes_id is not None:
                previous = assumptions.get(item.supersedes_id)
                if (
                    previous is None
                    or previous.status != "superseded"
                    or item.revision != previous.revision + 1
                    or previous.client_ref != item.client_ref
                    or previous.basis_refs != item.basis_refs
                ):
                    raise ValueError(
                        "revised assumption must retain its superseded history and basis"
                    )
            stored_assumption_evidence = assumption_evidence.get(item.assumption_id)
            if item.status == "pending":
                if stored_assumption_evidence is not None:
                    raise ValueError("pending assumption cannot have resolution evidence")
            elif item.status == "superseded":
                if stored_assumption_evidence is None:
                    raise ValueError("superseded assumption requires exact resolution evidence")
            elif not any(
                e.resulting_assumption_id == item.assumption_id
                for e in self.assumption_resolution_evidence
            ):
                raise ValueError("processed assumption requires its exact resolution evidence")
        for conflict_item in self.context_conflicts:
            conflict_item = ContextConflict.model_validate(conflict_item.model_dump())
            validate_reference(conflict_item.left_ref)
            validate_reference(conflict_item.right_ref)
            if conflict_item.status == "pending":
                required_gaps[f"context-conflict-{conflict_item.conflict_id}"] = (
                    "context_conflict",
                    conflict_item.conflict_id,
                    conflict_item.revision,
                )
                if conflict_item.conflict_id in conflict_evidence:
                    raise ValueError("pending conflict cannot have resolution evidence")
            elif conflict_item.conflict_id not in conflict_evidence:
                raise ValueError("resolved conflict requires its exact resolution evidence")
        actual_gaps = {
            gap.gap_id: (gap.target_kind, gap.target_id, gap.object_revision)
            for gap in self.completeness.gaps
            if gap.target_kind != "dimension" and gap.blocking
        }
        if actual_gaps != required_gaps:
            raise ValueError("completeness must retain all unresolved governance blockers")
        for evidence in (*self.assumption_resolution_evidence, *self.context_resolution_evidence):
            if (
                evidence.run_id != self.run_id
                or evidence.ledger_revision >= self.ledger.revision
                or evidence.resolved_at.utcoffset() is None
            ):
                raise ValueError(
                    "resolution evidence must bind this Run and committed Ledger revision"
                )
            for fact_id in evidence.decision_ids:
                fact = facts.get(fact_id)
                decision = fact.decision_evidence if fact is not None else None
                if (
                    decision is None
                    or decision.command_id != evidence.command_id
                    or decision.batch_id != evidence.batch_id
                    or decision.expected_revision != evidence.ledger_revision
                    or decision.actor_claim != evidence.actor_claim
                ):
                    raise ValueError(
                        "governance answer must bind an explicit same-command DECISION"
                    )
        for evidence in self.assumption_resolution_evidence:
            resolved_assumption = assumptions.get(evidence.assumption_id)
            target = assumptions.get(evidence.resulting_assumption_id)
            if (
                resolved_assumption is None
                or target is None
                or resolved_assumption.revision != evidence.object_revision
                or target.revision != evidence.resulting_revision
                or target.status != evidence.resulting_status
                or evidence.question_id != f"assumption-{resolved_assumption.assumption_id}"
                or (evidence.action == "revise") != (resolved_assumption.status == "superseded")
                or (
                    evidence.action == "revise"
                    and target.supersedes_id != resolved_assumption.assumption_id
                )
                or (evidence.action != "revise" and target != resolved_assumption)
            ):
                raise ValueError(
                    "assumption resolution must retain exact object versions and outcome"
                )
            product = bool(target.affected_dimensions) or target.product_impact != "none"
            dimensions = {facts[key].dimension for key in evidence.decision_ids}
            if target.status == "accepted" and product:
                if not target.affected_dimensions or dimensions != set(target.affected_dimensions):
                    raise ValueError(
                        "accepted product assumption requires each explicit dimension DECISION"
                    )
                for key in evidence.decision_ids:
                    decision_evidence = facts[key].decision_evidence
                    if (
                        decision_evidence is None
                        or target.assumption_id not in decision_evidence.resolved_assumption_ids
                    ):
                        raise ValueError("DecisionEvidence must bind the accepted assumption")
            elif evidence.decision_ids:
                raise ValueError(
                    "background/rejected assumptions cannot manufacture product decisions"
                )
        for conflict_resolution in self.context_resolution_evidence:
            conflict = conflicts.get(conflict_resolution.conflict_id)
            if (
                conflict is None
                or conflict.status != "resolved"
                or conflict.revision != conflict_resolution.object_revision
                or conflict_resolution.question_id != f"context-conflict-{conflict.conflict_id}"
            ):
                raise ValueError("conflict resolution requires its exact object and question")
            if conflict.dimension is not None:
                if (
                    conflict_resolution.action != "answer"
                    or len(conflict_resolution.decision_ids) != 1
                    or facts[conflict_resolution.decision_ids[0]].dimension != conflict.dimension
                    or conflict_resolution.excluded_reference_id is not None
                ):
                    raise ValueError("dimension conflict requires an explicit product answer")
            elif (
                conflict_resolution.decision_ids
                or conflict_resolution.action not in ("exclude", "irrelevant")
                or (
                    conflict_resolution.action == "exclude"
                    and conflict_resolution.excluded_reference_id
                    not in (conflict.left_ref.reference_id, conflict.right_ref.reference_id)
                )
            ):
                raise ValueError(
                    "reference conflict requires an explicit exclusion or irrelevant judgment"
                )

    def _validate_td_review_projection(self) -> None:
        if self.td_draft is None:
            if self.td_review is not None or self.td_review_records:
                raise ValueError("TD reviews require a TD draft")
            return
        if self.prd_draft is None or self.prd_approval is None or self.design_authority is None:
            raise ValueError("TD reviews require an approved PRD")
        binding = TdReviewBinding(
            run_id=self.run_id, prd_revision=self.prd_draft.revision,
            prd_content_hash=self.prd_draft.content_hash,
            td_revision=self.td_draft.revision, td_content_hash=self.td_draft.content_hash,
            authority_pack_hash=self.design_authority.content_hash,
            obligations_hash=td_obligations_hash(self.td_draft.obligations),
        )
        projection = self.td_review
        if projection is None or projection.binding != binding:
            raise ValueError("TD review projection must expose the current server binding")
        if projection.status == "ready" and (
            self.td_readiness is None or not self.td_readiness.ready
        ):
            raise ValueError("ready TD review requires current structural readiness")
        if not self.td_review_records:
            if not (
                projection
                == TdReviewProjection(binding=binding, status="missing", review_revision=0)
                or (
                    projection.status == "stale"
                    and projection.current_review_id is None
                    and projection.review_revision > 0
                    and not projection.blocking_finding_ids
                )
            ):
                raise ValueError("initial TD review must be missing at revision zero")
        else:
            ids = set()
            prior_id = None
            last_revision = 0
            previous: TdReviewRecord | None = None
            revisions = {item.revision: item for item in self.td_revisions}
            for record in self.td_review_records:
                historical_td = revisions.get(record.binding.td_revision)
                if historical_td is None or record.binding != binding.model_copy(
                    update={
                        "td_revision": historical_td.revision,
                        "td_content_hash": historical_td.content_hash,
                    }
                ):
                    raise ValueError("review must bind a retained TD and its frozen authority")
                old_findings = (
                    {item.finding_id: item for item in previous.findings} if previous else {}
                )
                current_findings = {item.finding_id: item for item in record.findings}
                if not set(old_findings) <= set(current_findings):
                    raise ValueError("review history cannot erase earlier findings")
                rechecks = {item.finding_id: item for item in record.rechecks}
                unresolved = {
                    key for key, item in old_findings.items() if item.disposition != "dismissed"
                }
                changed_revision = (
                    previous is not None
                    and record.binding.td_revision > previous.binding.td_revision
                )
                if (
                    len(rechecks) != len(record.rechecks)
                    or (changed_revision and set(rechecks) != unresolved)
                    or (not changed_revision and rechecks)
                    or (
                        previous is not None
                        and record.binding.td_revision < previous.binding.td_revision
                    )
                ):
                    raise ValueError("new TD reports require exact unresolved finding rechecks")
                for finding_id, finding in current_findings.items():
                    old = old_findings.get(finding_id)
                    if old is not None:
                        if finding.model_dump(
                            exclude={"disposition", "disposition_rationale"}
                        ) != old.model_dump(exclude={"disposition", "disposition_rationale"}):
                            raise ValueError("historical finding evidence is immutable")
                    else:
                        for excerpt, content in (
                            (finding.prd_excerpt, self.prd_draft.content),
                            (finding.td_excerpt, historical_td.content),
                        ):
                            if content[excerpt.start : excerpt.end] != excerpt.excerpt:
                                raise ValueError(
                                    "new finding must quote its bound document revision"
                                )
                    if not set(finding.obligation_ids) <= set(
                        record.reviewed_obligation_ids
                    ) or len(set(finding.obligation_ids)) != len(finding.obligation_ids):
                        raise ValueError("findings require known unique obligation references")
                for finding_id, recheck in rechecks.items():
                    finding = current_findings[finding_id]
                    if recheck.td_excerpt is not None:
                        quote = recheck.td_excerpt
                        if historical_td.content[quote.start : quote.end] != quote.excerpt:
                            raise ValueError("recheck must quote its current TD revision")
                    if recheck.outcome == "still_present":
                        if (
                            recheck.td_excerpt is None
                            or finding.disposition != old_findings[finding_id].disposition
                        ):
                            raise ValueError(
                                "still_present must retain its blocker and cite current TD"
                            )
                    elif (
                        finding.disposition != "dismissed"
                        or finding.disposition_rationale != recheck.rationale
                        or (
                            recheck.outcome == "fixed"
                            and previous is not None
                            and previous.binding.td_content_hash == record.binding.td_content_hash
                        )
                    ):
                        raise ValueError(
                            "resolved recheck requires changed text for fixed and a rationale"
                        )
                if set(record.reviewed_obligation_ids) != {
                    item.obligation_id for item in historical_td.obligations
                }:
                    raise ValueError("review coverage must match frozen obligations")
                previous = record
                if (
                    record.review_id in ids
                    or record.prior_review_id != prior_id
                    or record.review_revision <= last_revision
                    or record.binding.run_id != self.run_id
                    or record.reviewed_at.utcoffset() is None
                ):
                    raise ValueError("TD review history must preserve unique ordered human records")
                ids.add(record.review_id)
                prior_id = record.review_id
                last_revision = record.review_revision
            current = self.td_review_records[-1]
            blockers = tuple(
                item.finding_id for item in current.findings if item.disposition != "dismissed"
            )
            status = current.computed_status if current.binding == binding else "stale"
            if (
                projection.current_review_id != current.review_id
                or projection.review_revision < current.review_revision
                or projection.status != status
                or projection.blocking_finding_ids != blockers
            ):
                raise ValueError("TD review projection must match its retained evidence")
            if current.computed_status == "ready" and (
                blockers
                or current.human_conclusion != "no_conflict_observed"
                or set(current.reviewed_obligation_ids)
                != {item.obligation_id for item in self.td_draft.obligations}
            ):
                raise ValueError("ready TD review requires explicit full coverage without blockers")
        if self.td_approval is not None and (
            projection.status != "ready"
            or self.td_approval.review_id != projection.current_review_id
            or self.td_approval.expected_review_revision != projection.review_revision
        ):
            raise ValueError("TD approval must reference the current ready human review")

    @model_validator(mode="after")
    def validate_state_projection(self) -> "RunResponse":
        self._validate_admission_projection()
        self._validate_governance_projection()
        if self.prd_supporting_context != PrdSupportingContext(
            knowledge_citations=self.knowledge_citations,
            assumptions=self.assumptions,
        ):
            raise ValueError("PRD supporting context must match the validated Run references")
        if self.ledger.revision != self.completeness.ledger_revision:
            raise ValueError("completeness must describe the current Fact Ledger revision")

        if self.prd_draft is None:
            if (
                self.prd_blueprint is not None
                or self.prd_revisions
                or self.prd_readiness is not None
            ):
                raise ValueError("PRD planning and revision data require a PRD draft")
        else:
            if (
                self.prd_blueprint is None
                or self.prd_readiness is None
                or not self.prd_revisions
                or self.prd_revisions[-1] != self.prd_draft
                or tuple(revision.revision for revision in self.prd_revisions)
                != tuple(range(1, len(self.prd_revisions) + 1))
                or self.prd_blueprint.ledger_revision != self.ledger.revision
                or set(self.prd_blueprint.authoritative_fact_ids)
                != {fact.fact_id for fact in self.ledger.authoritative_facts}
                or self.prd_readiness.revision != self.prd_draft.revision
                or self.prd_readiness.content_hash != self.prd_draft.content_hash
            ):
                raise ValueError("PRD blueprint, revisions, readiness, and Ledger must agree")
        if self.prd_approval is not None and (
            self.prd_draft is None
            or self.prd_approval.revision != self.prd_draft.revision
            or self.prd_approval.content_hash != self.prd_draft.content_hash
            or self.prd_readiness is None
            or not self.prd_readiness.ready
        ):
            raise ValueError("PRD approval must freeze the ready current revision and hash")

        if self.prd_approval is None:
            if (
                self.design_authority is not None
                or self.td_blueprint is not None
                or self.technical_decision_requests
                or self.technical_decisions
                or self.td_draft is not None
                or self.td_approval is not None
                or self.delivery_spec is not None
                or self.artifact_envelopes
            ):
                raise ValueError("technical authority and artifacts require an approved PRD")
        elif (
            self.prd_draft is None
            or self.design_authority is None
            or self.td_blueprint is None
            or self.design_authority.prd_revision != self.prd_draft.revision
            or self.design_authority.prd_content_hash != self.prd_draft.content_hash
            or self.td_blueprint.prd_revision != self.prd_draft.revision
            or self.td_blueprint.prd_content_hash != self.prd_draft.content_hash
        ):
            raise ValueError("technical authority must bind the approved PRD")

        if self.td_draft is not None and (
            self.design_authority is None
            or self.prd_draft is None
            or self.td_draft.prd_revision != self.prd_draft.revision
            or self.td_draft.prd_content_hash != self.prd_draft.content_hash
            or self.td_draft.authority_pack_hash != self.design_authority.content_hash
        ):
            raise ValueError("TD draft must bind the approved PRD and authority pack")

        if self.td_draft is None:
            if self.td_revisions or self.td_readiness is not None:
                raise ValueError("TD history and readiness require a TD draft")
        elif (
            not self.td_revisions or self.td_revisions[-1] != self.td_draft
            or tuple(item.revision for item in self.td_revisions)
            != tuple(range(1, len(self.td_revisions) + 1))
            or self.td_readiness is None
            or self.td_readiness.revision != self.td_draft.revision
            or self.td_readiness.content_hash != self.td_draft.content_hash
            or any((item.prd_revision, item.prd_content_hash, item.authority_pack_hash,
                    item.obligations) != (self.td_draft.prd_revision,
                    self.td_draft.prd_content_hash, self.td_draft.authority_pack_hash,
                    self.td_draft.obligations) for item in self.td_revisions)
        ):
            raise ValueError("TD history and readiness must preserve frozen bindings")
        self._validate_td_review_projection()

        if self.status is RunStatus.AWAITING_CLARIFICATION:
            valid = (
                self.prd_draft is None
                and self.prd_blueprint is None
                and not self.prd_revisions
                and self.prd_approval is None
                and self.td_draft is None
                and self.td_approval is None
                and self.delivery_spec is None
                and (
                    not self.completeness.is_complete
                    or any(
                        item.status is SourceClaimStatus.PENDING
                        for item in self.pending_source_claims
                    )
                )
                and self.clarification_batch is not None
                and self.clarification_batch.ledger_revision == self.ledger.revision
                and set(self.clarification_batch.required_candidate_ids)
                == {
                    item.candidate_id
                    for item in self.pending_source_claims
                    if item.status is SourceClaimStatus.PENDING
                }
                and set(self.clarification_batch.blocking_gap_ids)
                == {gap.gap_id for gap in self.completeness.gaps if gap.blocking}
                and self.available_commands == (AvailableCommand.SUBMIT_CLARIFICATION,)
            )
        elif self.status is RunStatus.PRD_AWAITING_APPROVAL:
            valid = (
                self.prd_draft is not None
                and self.prd_approval is None
                and self.td_draft is None
                and self.td_approval is None
                and self.delivery_spec is None
                and self.completeness.is_complete
                and self.prd_readiness is not None
                and self.available_commands
                == (
                    (AvailableCommand.REVISE_PRD, AvailableCommand.APPROVE_PRD)
                    if self.prd_readiness.ready
                    else (AvailableCommand.REVISE_PRD,)
                )
            )
        elif self.status is RunStatus.TD_AWAITING_DECISION:
            valid = (
                self.prd_approval is not None
                and self.design_authority is not None
                and self.td_blueprint is not None
                and self.td_draft is None
                and self.td_approval is None
                and self.delivery_spec is None
                and bool(self.technical_decision_requests)
                and not self.technical_decisions
                and not self.artifact_envelopes
                and self.available_commands == (AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,)
            )
        elif self.status is RunStatus.TD_AWAITING_APPROVAL:
            valid = (
                self.prd_draft is not None
                and self.prd_approval is not None
                and self.prd_approval.revision == self.prd_draft.revision
                and self.prd_readiness is not None
                and self.prd_readiness.ready
                and self.td_draft is not None
                and self.td_approval is None
                and self.delivery_spec is None
                and not self.technical_decision_requests
                and not self.artifact_envelopes
                and self.completeness.is_complete
                and self.td_review is not None
                and self.available_commands == (
                    (AvailableCommand.RECORD_TD_REVIEW, AvailableCommand.REVISE_TD,
                     AvailableCommand.APPROVE_TD)
                    if self.td_review.status == "ready"
                    else (AvailableCommand.RECORD_TD_REVIEW, AvailableCommand.REVISE_TD)
                )
            )
        else:
            valid = (
                self.prd_draft is not None
                and self.prd_approval is not None
                and self.prd_approval.revision == self.prd_draft.revision
                and self.prd_readiness is not None
                and self.prd_readiness.ready
                and self.td_draft is not None
                and self.td_approval is not None
                and self.td_approval.revision == self.td_draft.revision
                and self.delivery_spec is not None
                and len(self.artifact_envelopes) == 3
                and self.completeness.is_complete
                and self.available_commands == ()
            )

        if self.status is not RunStatus.AWAITING_CLARIFICATION and any(
            item.status is SourceClaimStatus.PENDING for item in self.pending_source_claims
        ):
            raise ValueError("all source candidates require explicit processing before PRD")
        if not valid:
            raise ValueError("Run status, approvals, artifacts, and commands are inconsistent")

        if self.delivery_spec is not None and (
            self.delivery_spec.run_id != self.run_id
            or self.prd_draft is None
            or self.delivery_spec.prd.revision != self.prd_draft.revision
            or self.delivery_spec.prd.content_hash != self.prd_draft.content_hash
            or self.td_draft is None
            or self.delivery_spec.td.revision != self.td_draft.revision
            or self.delivery_spec.td.content_hash != self.td_draft.content_hash
            or self.design_authority is None
            or self.delivery_spec.authority_pack_hash != self.design_authority.content_hash
            or {envelope.artifact.kind for envelope in self.artifact_envelopes}
            != {ArtifactKind.PRD, ArtifactKind.TD, ArtifactKind.DELIVERY_SPEC}
        ):
            raise ValueError("DeliverySpec must reference the approved Run artifacts")

        return self

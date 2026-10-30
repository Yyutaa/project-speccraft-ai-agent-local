"""Creation-only context capture and pure atomic governance proposals."""

from datetime import UTC, datetime
from itertools import combinations
from uuid import uuid4

from deliveryflow_contracts.facts import (
    CompletenessResult,
    FactLedger,
    GapSignal,
    RequirementFact,
    SubmitClarificationRequest,
)
from deliveryflow_contracts.knowledge import (
    Assumption,
    AssumptionResolutionEvidence,
    ContextConflict,
    ContextReference,
    ContextResolutionEvidence,
    InputReference,
    KnowledgeCitation,
)
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_contracts.sources import (
    PendingSourceClaim,
    SourceRecord,
)

from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.source_admission import make_source_record


class ContextGovernanceError(ValueError):
    """Stable error code mapped by the Runner's public write boundary."""


def capture_governance(
    request: CreateRunRequest,
    harness: RepositoryHarness,
    records: tuple[SourceRecord, ...],
    candidates: tuple[PendingSourceClaim, ...],
) -> tuple[
    tuple[SourceRecord, ...],
    tuple[PendingSourceClaim, ...],
    tuple[KnowledgeCitation, ...],
    tuple[Assumption, ...],
    tuple[ContextConflict, ...],
]:
    run_id = records[0].run_id
    selected = request.claim_selections
    candidates = tuple(
        PendingSourceClaim.model_validate(
            {
                **candidate.model_dump(),
                "client_ref": selected[i].client_ref if selected else "requirement_candidate",
                **(
                    {
                        key: getattr(selected[i], key)
                        for key in ("subject_key", "dimension", "rule_excerpt")
                    }
                    if selected
                    else {}
                ),
            }
        )
        for i, candidate in enumerate(candidates)
    )
    for candidate in candidates:
        if candidate.rule_excerpt is not None and candidate.rule_excerpt not in candidate.excerpt:
            raise ContextGovernanceError("invalid_rule_excerpt")
    references: dict[str, ContextReference] = {}
    for candidate in candidates:
        assert candidate.client_ref is not None
        references[candidate.client_ref] = ContextReference(
            kind="candidate",
            reference_id=candidate.candidate_id,
            **{
                key: getattr(candidate, key)
                for key in ("source_id", "source_sha256", "start", "end", "excerpt")
            },
        )
    assumption_ids = {item.client_ref: str(uuid4()) for item in request.assumptions}
    all_records = list(records)
    citations = []
    for item in request.knowledge_selections:
        snapshot = harness.read_knowledge(item.path)
        source = next(
            (
                record
                for record in all_records
                if record.snapshot.normalized_path == snapshot.normalized_path
            ),
            None,
        )
        if source is None:
            source = make_source_record(run_id, snapshot, harness.repository_id)
            all_records.append(source)
        try:
            candidate_ids = tuple(
                references[ref].reference_id
                for ref in item.related_candidate_refs
                if references[ref].kind == "candidate"
            )
            if len(candidate_ids) != len(item.related_candidate_refs):
                raise KeyError("candidate")
            related_assumptions = tuple(assumption_ids[ref] for ref in item.related_assumption_refs)
        except KeyError as error:
            raise ContextGovernanceError("knowledge_citation_reference_invalid") from error
        try:
            citation = KnowledgeCitation(
                citation_id=str(uuid4()),
                client_ref=item.client_ref,
                source_id=source.source_id,
                source_sha256=snapshot.sha256,
                start=item.start,
                end=item.end,
                excerpt=snapshot.content[item.start : item.end],
                purpose=item.purpose,
                related_candidate_ids=candidate_ids,
                related_assumption_ids=related_assumptions,
                subject_key=item.subject_key,
                dimension=item.dimension,
                rule_excerpt=item.rule_excerpt,
            )
        except ValueError as error:
            raise ContextGovernanceError("knowledge_citation_invalid") from error
        citations.append(citation)
        references[item.client_ref] = ContextReference(
            kind="citation",
            reference_id=citation.citation_id,
            **{
                key: getattr(citation, key)
                for key in ("source_id", "source_sha256", "start", "end", "excerpt")
            },
        )
    if sum(len(item.excerpt.encode("utf-8")) for item in citations) > 16 * 1024:
        raise ContextGovernanceError("knowledge_too_large")

    def resolve(ref: InputReference) -> ContextReference:
        if ref.kind == "source" and ref.client_ref == "requirement_source":
            source = records[0]
            assert ref.start is not None and ref.end is not None
            return ContextReference(
                kind="source",
                reference_id=source.source_id,
                source_id=source.source_id,
                source_sha256=source.snapshot.sha256,
                start=ref.start,
                end=ref.end,
                excerpt=source.snapshot.content[ref.start : ref.end],
            )
        value = references.get(ref.client_ref)
        if value is None or value.kind != ref.kind:
            raise ContextGovernanceError("invalid_context_reference")
        return value

    assumptions = tuple(
        Assumption(
            **item.model_dump(exclude={"basis_refs"}),
            assumption_id=assumption_ids[item.client_ref],
            revision=1,
            producer_kind="user",
            basis_refs=tuple(resolve(ref) for ref in item.basis_refs),
        )
        for item in request.assumptions
    )
    conflicts = [
        ContextConflict(
            conflict_id=str(uuid4()),
            client_ref=item.client_ref,
            left_ref=resolve(item.left_ref),
            right_ref=resolve(item.right_ref),
            dimension=item.dimension,
            discoverer_kind="user",
            reason=item.reason,
        )
        for item in request.context_conflicts
    ]
    rule_items: list[PendingSourceClaim | KnowledgeCitation] = [*candidates, *citations]
    rules = [item for item in rule_items if item.subject_key is not None]
    for left, right in combinations(rules, 2):
        if (
            left.subject_key == right.subject_key
            and left.dimension == right.dimension
            and left.rule_excerpt != right.rule_excerpt
            and (isinstance(left, KnowledgeCitation) or isinstance(right, KnowledgeCitation))
        ):
            assert left.client_ref is not None and right.client_ref is not None
            conflicts.append(
                ContextConflict(
                    conflict_id=str(uuid4()),
                    client_ref=f"auto:{left.client_ref}:{right.client_ref}",
                    left_ref=references[left.client_ref],
                    right_ref=references[right.client_ref],
                    dimension=left.dimension,
                    discoverer_kind="deterministic_metadata",
                    reason="显式声明的同主题同维度规则摘录不一致，需人工确认；此结果不代表语义矛盾检测。",
                )
            )
    return tuple(all_records), candidates, tuple(citations), assumptions, tuple(conflicts)


def add_governance_gaps(
    completeness: CompletenessResult,
    assumptions: tuple[Assumption, ...],
    conflicts: tuple[ContextConflict, ...],
) -> CompletenessResult:
    gaps = list(completeness.gaps)
    for item in assumptions:
        if item.blocking:
            gaps.append(
                GapSignal(
                    gap_id=f"assumption-{item.assumption_id}",
                    dimension=None,
                    target_kind="assumption",
                    target_id=item.assumption_id,
                    object_revision=item.revision,
                    blocking=True,
                    reason="假设尚未明确裁决",
                    ledger_revision=completeness.ledger_revision,
                )
            )
    for conflict in conflicts:
        if conflict.status == "pending":
            gaps.append(
                GapSignal(
                    gap_id=f"context-conflict-{conflict.conflict_id}",
                    dimension=conflict.dimension,
                    target_kind="context_conflict",
                    target_id=conflict.conflict_id,
                    object_revision=conflict.revision,
                    blocking=True,
                    reason=conflict.reason,
                    ledger_revision=completeness.ledger_revision,
                )
            )
    return CompletenessResult(ledger_revision=completeness.ledger_revision, gaps=tuple(gaps))


def resolve_governance(
    run: RunResponse,
    request: SubmitClarificationRequest,
    decisions: tuple[RequirementFact, ...],
    ledger: FactLedger,
) -> dict[str, object]:
    assert run.clarification_batch is not None
    by_question = {
        item.decision_evidence.question_id: item
        for item in decisions
        if item.decision_evidence is not None
    }
    evidence_base = dict(
        run_id=run.run_id,
        batch_id=request.batch_id,
        batch_revision=request.batch_revision,
        command_id=request.command_id,
        ledger_revision=request.expected_revision,
        actor_claim=request.actor_claim,
    )
    evidence_base["resolved_at"] = datetime.now(UTC)
    assumptions = list(run.assumptions)
    assumption_evidence = list(run.assumption_resolution_evidence)
    resolved_by_decision: dict[str, list[str]] = {}
    for resolution in request.assumption_resolutions:
        item = next((a for a in assumptions if a.assumption_id == resolution.assumption_id), None)
        if (
            item is None
            or item.status != "pending"
            or item.revision != resolution.expected_assumption_revision
        ):
            raise ContextGovernanceError("assumption_revision_conflict")
        if resolution.question_id != f"assumption-{item.assumption_id}":
            raise ContextGovernanceError("assumption_question_invalid")
        target = item
        action = resolution.action
        if resolution.action == "revise":
            assert (
                resolution.revised_assumption is not None and resolution.revised_action is not None
            )
            assumptions[assumptions.index(item)] = item.model_copy(update={"status": "superseded"})
            target = Assumption(
                **{
                    **item.model_dump(),
                    **resolution.revised_assumption.model_dump(),
                    "assumption_id": str(uuid4()),
                    "revision": item.revision + 1,
                    "supersedes_id": item.assumption_id,
                }
            )
            action = resolution.revised_action
        selected = [by_question.get(key) for key in resolution.final_answer_question_ids]
        if any(fact is None for fact in selected):
            raise ContextGovernanceError("assumption_answer_required")
        linked = tuple(fact for fact in selected if fact is not None)
        product = bool(target.affected_dimensions) or target.product_impact != "none"
        if action == "accept" and product:
            if not target.affected_dimensions or {f.dimension for f in linked} != set(
                target.affected_dimensions
            ):
                raise ContextGovernanceError("assumption_answer_required")
        elif linked:
            raise ContextGovernanceError("unexpected_context_answer")
        target = target.model_copy(
            update={"status": "accepted" if action == "accept" else "rejected"}
        )
        if resolution.action == "revise":
            assumptions.append(target)
        else:
            assumptions[assumptions.index(item)] = target
        for fact in linked:
            resolved_by_decision.setdefault(fact.fact_id, []).append(target.assumption_id)
        assumption_evidence.append(
            AssumptionResolutionEvidence.model_validate(
                {
                    **evidence_base,
                    "question_id": resolution.question_id,
                    "rationale": resolution.rationale,
                    "assumption_id": item.assumption_id,
                    "object_revision": item.revision,
                    "action": resolution.action,
                    "resulting_assumption_id": target.assumption_id,
                    "resulting_revision": target.revision,
                    "resulting_status": target.status,
                    "decision_ids": tuple(f.fact_id for f in linked),
                }
            )
        )
    conflicts = list(run.context_conflicts)
    conflict_evidence = list(run.context_resolution_evidence)
    for resolution_c in request.context_conflict_resolutions:
        conflict = next((c for c in conflicts if c.conflict_id == resolution_c.conflict_id), None)
        if (
            conflict is None
            or conflict.status != "pending"
            or conflict.revision != resolution_c.expected_conflict_revision
        ):
            raise ContextGovernanceError("context_conflict_revision_conflict")
        if resolution_c.question_id != f"context-conflict-{conflict.conflict_id}":
            raise ContextGovernanceError("context_conflict_question_invalid")
        decision_ids: tuple[str, ...] = ()
        if conflict.dimension is not None:
            conflict_answer = by_question.get(resolution_c.final_answer_question_id or "")
            if (
                resolution_c.action != "answer"
                or conflict_answer is None
                or conflict_answer.dimension != conflict.dimension
                or resolution_c.excluded_reference_id is not None
            ):
                raise ContextGovernanceError("context_conflict_answer_required")
            decision_ids = (conflict_answer.fact_id,)
        elif (
            resolution_c.action not in ("exclude", "irrelevant")
            or resolution_c.final_answer_question_id is not None
            or (
                resolution_c.action == "exclude"
                and resolution_c.excluded_reference_id
                not in (conflict.left_ref.reference_id, conflict.right_ref.reference_id)
            )
            or (
                resolution_c.action == "irrelevant"
                and resolution_c.excluded_reference_id is not None
            )
        ):
            raise ContextGovernanceError("invalid_context_resolution")
        conflicts[conflicts.index(conflict)] = conflict.model_copy(update={"status": "resolved"})
        conflict_evidence.append(
            ContextResolutionEvidence.model_validate(
                {
                    **evidence_base,
                    "question_id": resolution_c.question_id,
                    "rationale": resolution_c.rationale,
                    "conflict_id": conflict.conflict_id,
                    "object_revision": conflict.revision,
                    "action": resolution_c.action,
                    "excluded_reference_id": resolution_c.excluded_reference_id,
                    "decision_ids": decision_ids,
                }
            )
        )
    facts = []
    for fact in ledger.facts:
        if fact.fact_id in resolved_by_decision and fact.decision_evidence is not None:
            fact = fact.model_copy(
                update={
                    "decision_evidence": fact.decision_evidence.model_copy(
                        update={
                            "resolved_assumption_ids": tuple(resolved_by_decision[fact.fact_id])
                        }
                    )
                }
            )
        facts.append(fact)
    admitted = {
        fact.admission_evidence.candidate_id: fact.fact_id
        for fact in facts
        if fact.admission_evidence is not None
    }
    citations = tuple(
        c.model_copy(
            update={
                "related_fact_ids": tuple(
                    admitted[key] for key in c.related_candidate_ids if key in admitted
                )
            }
        )
        for c in run.knowledge_citations
    )
    return {
        "assumptions": tuple(assumptions),
        "context_conflicts": tuple(conflicts),
        "assumption_resolution_evidence": tuple(assumption_evidence),
        "context_resolution_evidence": tuple(conflict_evidence),
        "knowledge_citations": citations,
        "ledger": FactLedger(revision=ledger.revision, facts=tuple(facts)),
    }

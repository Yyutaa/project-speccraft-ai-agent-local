"""Finite reference context and explicit human assumption/conflict governance."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from deliveryflow_contracts.dimensions import FactDimension
from deliveryflow_contracts.sources import AdmissionModel, NonBlank, Sha256


class RuleMetadata(AdmissionModel):
    subject_key: NonBlank | None = None
    dimension: FactDimension | None = None
    rule_excerpt: NonBlank | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> "RuleMetadata":
        if (self.subject_key is not None or self.rule_excerpt is not None) and (
            self.subject_key is None or self.dimension is None or self.rule_excerpt is None
        ):
            raise ValueError(
                "structured rule requires subject_key, dimension and exact rule_excerpt"
            )
        return self


class KnowledgeSelection(RuleMetadata):
    client_ref: NonBlank
    path: NonBlank
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    purpose: NonBlank
    related_candidate_refs: tuple[NonBlank, ...] = ()
    related_assumption_refs: tuple[NonBlank, ...] = ()


class InputReference(AdmissionModel):
    kind: Literal["source", "candidate", "citation"]
    client_ref: NonBlank = Field(
        description=(
            "Creation alias; default source is requirement_source "
            "and default whole-text candidate is requirement_candidate."
        )
    )
    start: int | None = Field(default=None, ge=0, strict=True)
    end: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def validate_range(self) -> "InputReference":
        if self.kind == "source":
            if self.start is None or self.end is None or self.start >= self.end:
                raise ValueError("source reference requires an exact nonempty interval")
        elif self.start is not None or self.end is not None:
            raise ValueError("candidate/citation reference uses its stored exact interval")
        return self


class ContextReference(AdmissionModel):
    kind: Literal["source", "candidate", "citation"]
    reference_id: NonBlank
    source_id: NonBlank
    source_sha256: Sha256
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    excerpt: NonBlank

    @model_validator(mode="after")
    def validate_range(self) -> "ContextReference":
        if self.start >= self.end or self.end - self.start != len(self.excerpt):
            raise ValueError("reference must retain its exact Unicode interval")
        return self


class AssumptionValues(AdmissionModel):
    statement: NonBlank
    affected_dimensions: tuple[FactDimension, ...] = ()
    risk: Literal["low", "high", "unknown"] = "unknown"
    product_impact: Literal["none", "present", "unknown"] = "unknown"

    @model_validator(mode="after")
    def unique_dimensions(self) -> "AssumptionValues":
        if len(self.affected_dimensions) != len(set(self.affected_dimensions)):
            raise ValueError("affected dimensions must be unique")
        return self


class AssumptionInput(AssumptionValues):
    client_ref: NonBlank
    basis_refs: tuple[InputReference, ...] = Field(min_length=1)


class Assumption(AssumptionValues):
    assumption_id: NonBlank
    client_ref: NonBlank
    revision: int = Field(ge=1, strict=True)
    producer_kind: Literal["user", "fake", "model"]
    basis_refs: tuple[ContextReference, ...] = Field(min_length=1)
    status: Literal["pending", "accepted", "rejected", "superseded"] = "pending"
    supersedes_id: NonBlank | None = None

    @property
    def blocking(self) -> bool:
        return self.status == "pending" and bool(
            self.affected_dimensions or self.product_impact != "none" or self.risk != "low"
        )


class KnowledgeCitation(RuleMetadata):
    citation_id: NonBlank
    client_ref: NonBlank
    source_id: NonBlank
    source_sha256: Sha256
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    excerpt: NonBlank
    purpose: NonBlank
    related_candidate_ids: tuple[NonBlank, ...] = ()
    related_fact_ids: tuple[NonBlank, ...] = ()
    related_assumption_ids: tuple[NonBlank, ...] = ()

    @model_validator(mode="after")
    def validate_excerpt(self) -> "KnowledgeCitation":
        if self.start >= self.end or self.end - self.start != len(self.excerpt):
            raise ValueError("citation must retain its exact Unicode interval")
        if len(self.excerpt.encode("utf-8")) > 2048:
            raise ValueError("knowledge excerpt exceeds 2 KiB UTF-8")
        if self.rule_excerpt is not None and self.rule_excerpt not in self.excerpt:
            raise ValueError("rule_excerpt must occur within the selected citation")
        for values in (
            self.related_candidate_ids,
            self.related_fact_ids,
            self.related_assumption_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("citation related identities must be unique")
        return self


class ContextConflictInput(AdmissionModel):
    client_ref: NonBlank
    left_ref: InputReference
    right_ref: InputReference
    dimension: FactDimension | None = None
    reason: NonBlank


class ContextConflict(AdmissionModel):
    conflict_id: NonBlank
    client_ref: NonBlank
    left_ref: ContextReference
    right_ref: ContextReference
    dimension: FactDimension | None = None
    discoverer_kind: Literal["user", "fake", "model", "deterministic_metadata"]
    reason: NonBlank
    status: Literal["pending", "resolved"] = "pending"
    revision: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode="after")
    def distinct_sides(self) -> "ContextConflict":
        if self.left_ref == self.right_ref:
            raise ValueError("conflict must identify two distinct references")
        return self


class AssumptionResolution(AdmissionModel):
    question_id: NonBlank
    assumption_id: NonBlank
    expected_assumption_revision: int = Field(ge=1, strict=True)
    action: Literal["accept", "reject", "revise"]
    rationale: NonBlank
    final_answer_question_ids: tuple[NonBlank, ...] = ()
    revised_assumption: AssumptionValues | None = None
    revised_action: Literal["accept", "reject"] | None = None

    @model_validator(mode="after")
    def validate_revision(self) -> "AssumptionResolution":
        if (self.action == "revise") != (
            self.revised_assumption is not None and self.revised_action is not None
        ):
            raise ValueError("revise requires new values and explicit revised_action")
        if self.action != "revise" and (
            self.revised_assumption is not None or self.revised_action is not None
        ):
            raise ValueError("revision fields are only allowed for revise")
        if len(self.final_answer_question_ids) != len(set(self.final_answer_question_ids)):
            raise ValueError("final answer references must be unique")
        return self


class ContextConflictResolution(AdmissionModel):
    question_id: NonBlank
    conflict_id: NonBlank
    expected_conflict_revision: int = Field(ge=1, strict=True)
    action: Literal["answer", "exclude", "irrelevant"]
    rationale: NonBlank
    final_answer_question_id: NonBlank | None = None
    excluded_reference_id: NonBlank | None = None


class ResolutionEvidence(AdmissionModel):
    run_id: NonBlank
    question_id: NonBlank
    batch_id: NonBlank
    batch_revision: int = Field(ge=1)
    command_id: NonBlank
    ledger_revision: int = Field(ge=1)
    actor_claim: NonBlank
    rationale: NonBlank
    resolved_at: datetime
    decision_ids: tuple[NonBlank, ...] = ()


class AssumptionResolutionEvidence(ResolutionEvidence):
    assumption_id: NonBlank
    object_revision: int = Field(ge=1)
    action: Literal["accept", "reject", "revise"]
    resulting_assumption_id: NonBlank
    resulting_revision: int = Field(ge=1)
    resulting_status: Literal["accepted", "rejected"]


class ContextResolutionEvidence(ResolutionEvidence):
    conflict_id: NonBlank
    object_revision: int = Field(ge=1)
    action: Literal["answer", "exclude", "irrelevant"]
    excluded_reference_id: NonBlank | None = None

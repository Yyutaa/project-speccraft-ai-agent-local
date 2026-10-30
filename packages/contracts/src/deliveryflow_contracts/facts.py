"""Contracts for evidence-backed requirement facts and user clarification."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deliveryflow_contracts.dimensions import FactDimension as FactDimension
from deliveryflow_contracts.governance import GovernanceWriteRequest
from deliveryflow_contracts.knowledge import AssumptionResolution, ContextConflictResolution
from deliveryflow_contracts.sources import (
    ClarificationResolution,
    SourceAdmissionEvidence,
    SourceClaimAction,
    SourceClaimReview,
)


class FactKind(StrEnum):
    FACT = "fact"
    DECISION = "decision"


class SourceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt: str = Field(min_length=1, pattern=r".*\S.*")


class DecisionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    answer: str = Field(min_length=1, pattern=r".*\S.*")
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    supporting_citation_ids: tuple[str, ...] = ()
    resolved_assumption_ids: tuple[str, ...] = ()
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RequirementFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str = Field(min_length=1)
    kind: FactKind
    dimension: FactDimension | None
    claim: str = Field(min_length=1, pattern=r".*\S.*")
    source: SourceEvidence | None = None
    decision_evidence: DecisionEvidence | None = None
    source_id: str | None = Field(default=None, min_length=1)
    admission_evidence: SourceAdmissionEvidence | None = None

    @model_validator(mode="after")
    def validate_authority_evidence(self) -> "RequirementFact":
        if self.kind is FactKind.FACT:
            if self.source is None or self.decision_evidence is not None:
                raise ValueError(
                    "FACT requires source evidence and cannot contain decision evidence"
                )
        elif self.dimension is None or self.decision_evidence is None or self.source is not None:
            raise ValueError(
                "DECISION requires a dimension and decision evidence, not source evidence"
            )
        elif self.decision_evidence.answer != self.claim:
            raise ValueError("claim must match decision evidence answer")
        if (
            self.kind is FactKind.FACT
            or self.source_id is not None
            or self.admission_evidence is not None
        ):
            evidence = self.admission_evidence
            if (
                self.kind is not FactKind.FACT
                or evidence is None
                or self.source is None
                or evidence.action is not SourceClaimAction.ACCEPT
                or self.source_id != evidence.source_id
                or self.source.sha256 != evidence.source_sha256
                or self.source.excerpt != evidence.excerpt
                or self.claim != evidence.excerpt.strip()
                or self.dimension != evidence.dimension
            ):
                raise ValueError("admitted FACT must match its precise admission evidence")
        return self


class FactLedger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    facts: tuple[RequirementFact, ...]

    @model_validator(mode="after")
    def require_unique_fact_ids(self) -> "FactLedger":
        candidate_versions: set[tuple[str, str, int]] = set()
        intervals: set[tuple[str, str, int, int]] = set()
        for fact in self.facts:
            validated = RequirementFact.model_validate(fact.model_dump())
            evidence = validated.admission_evidence
            if evidence is not None:
                key = (evidence.run_id, evidence.candidate_id, evidence.candidate_revision)
                if key in candidate_versions:
                    raise ValueError("a source candidate version can produce only one FACT")
                candidate_versions.add(key)
                interval = (evidence.run_id, evidence.source_id, evidence.start, evidence.end)
                if interval in intervals:
                    raise ValueError("source admission intervals must be unique")
                intervals.add(interval)
        ids = [fact.fact_id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact IDs must be unique")
        return self

    @property
    def authoritative_facts(self) -> tuple[RequirementFact, ...]:
        decisions = {
            fact.dimension: fact.fact_id for fact in self.facts if fact.kind is FactKind.DECISION
        }
        return tuple(
            fact
            for fact in self.facts
            if (fact.kind is FactKind.DECISION and decisions.get(fact.dimension) == fact.fact_id)
            or (
                fact.kind is FactKind.FACT
                and (fact.dimension is None or fact.dimension not in decisions)
            )
        )

    @property
    def authoritative_view(self) -> tuple[str, ...]:
        return tuple(fact.claim for fact in self.authoritative_facts)


class GapSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gap_id: str = Field(min_length=1)
    dimension: FactDimension | None
    target_kind: Literal["dimension", "assumption", "context_conflict"] = "dimension"
    target_id: str | None = None
    object_revision: int | None = None
    blocking: bool
    reason: str = Field(min_length=1)
    ledger_revision: int = Field(ge=1)


class CompletenessResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ledger_revision: int = Field(ge=1)
    gaps: tuple[GapSignal, ...]

    @model_validator(mode="after")
    def validate_gap_revisions(self) -> "CompletenessResult":
        if any(gap.ledger_revision != self.ledger_revision for gap in self.gaps):
            raise ValueError("completeness gaps must match the ledger revision")
        gap_ids = [gap.gap_id for gap in self.gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("gap IDs must be unique")
        return self

    @property
    def is_complete(self) -> bool:
        return not any(gap.blocking for gap in self.gaps)


class ClarificationOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: str = Field(min_length=1)
    label: str = Field(min_length=1, pattern=r".*\S.*")


class ClarificationProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str = Field(min_length=1)
    target_kind: Literal["dimension", "assumption", "context_conflict"] = "dimension"
    target_id: str | None = None
    object_revision: int | None = None
    gap_id: str = Field(min_length=1)
    question: str = Field(min_length=1, pattern=r".*\S.*")
    options: tuple[ClarificationOption, ...] = Field(min_length=1)
    recommended_option_id: str | None = None
    recommendation_reason: str | None = Field(default=None, pattern=r".*\S.*")

    @model_validator(mode="after")
    def validate_recommendation(self) -> "ClarificationProposal":
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("clarification option IDs must be unique")
        if self.recommended_option_id is not None:
            if self.recommended_option_id not in option_ids or not self.recommendation_reason:
                raise ValueError("recommended option must exist and include a reason")
        elif self.recommendation_reason is not None:
            raise ValueError("recommendation reason requires a recommended option")
        return self


class ClarificationBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    ledger_revision: int = Field(ge=1)
    gap_ids: tuple[str, ...]
    blocking_gap_ids: tuple[str, ...]
    proposals: tuple[ClarificationProposal, ...]
    required_candidate_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_blocking_gap_coverage(self) -> "ClarificationBatch":
        if len(self.required_candidate_ids) != len(set(self.required_candidate_ids)):
            raise ValueError("required candidate IDs must be unique")
        proposal_ids = [proposal.question_id for proposal in self.proposals]
        proposal_gap_ids = [proposal.gap_id for proposal in self.proposals]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("clarification question IDs must be unique")
        if len(proposal_gap_ids) != len(set(proposal_gap_ids)):
            raise ValueError("each gap must have one clarification proposal")
        if len(self.gap_ids) != len(set(self.gap_ids)):
            raise ValueError("gap IDs in a clarification batch must be unique")
        if not set(self.blocking_gap_ids).issubset(self.gap_ids):
            raise ValueError("blocking gaps must belong to the completeness result")
        if not set(proposal_gap_ids).issubset(self.gap_ids):
            raise ValueError("clarification proposals must refer to a known gap")
        if not set(self.blocking_gap_ids).issubset(proposal_gap_ids):
            raise ValueError("clarification batch must cover every blocking gap")
        return self


# Preserve the public import while using the strict three-way resolution contract.
ClarificationAnswer = ClarificationResolution


class SubmitClarificationRequest(GovernanceWriteRequest):
    expected_revision: int = Field(ge=1, strict=True)
    batch_id: str = Field(min_length=1)
    batch_revision: int = Field(ge=1, strict=True)
    command_id: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    user_confirmed: Literal[True]
    source_reviews: tuple[SourceClaimReview, ...]
    answers: tuple[ClarificationResolution, ...]
    assumption_resolutions: tuple[AssumptionResolution, ...] = ()
    context_conflict_resolutions: tuple[ContextConflictResolution, ...] = ()

    @field_validator("user_confirmed", mode="before")
    @classmethod
    def require_explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("user_confirmed must be explicitly true")
        return value

    @model_validator(mode="after")
    def require_unique_questions(self) -> "SubmitClarificationRequest":
        question_ids = (
            [answer.question_id for answer in self.answers]
            + [item.question_id for item in self.assumption_resolutions]
            + [item.question_id for item in self.context_conflict_resolutions]
        )
        review_ids = [review.review_id for review in self.source_reviews]
        candidate_ids = [review.candidate_id for review in self.source_reviews]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("each clarification question can be answered once")
        if len(review_ids) != len(set(review_ids)) or len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("source reviews and candidate IDs must be unique")
        return self

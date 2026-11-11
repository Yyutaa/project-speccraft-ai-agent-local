"""Public TD quality evidence and bounded patch requests."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.governance import GovernanceWriteRequest
from deliveryflow_contracts.td import TdSectionId


class QualityIssueRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(min_length=1)
    validator_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    authority_ref: str
    producer_kind: Literal["deterministic", "model"] = "deterministic"
    disposition: Literal["repair", "technical_decision", "product_change"] = "repair"
    suggestion: str = ""
    rule_version: str = "td-quality-v1"
    evidence_start: int | None = Field(default=None, ge=0)
    evidence_end: int | None = Field(default=None, gt=0)
    evidence: str = Field(min_length=1)
    severity: Literal["blocker", "major"]
    status: Literal["open", "reopened", "resolved", "failed", "accepted"]
    attempts: int = Field(ge=0, le=3, strict=True)
    last_failure: str | None = None
    first_td_revision: int = Field(default=1, ge=1)
    latest_td_revision: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_history(self) -> "QualityIssueRecord":
        if self.first_td_revision > self.latest_td_revision:
            raise ValueError("issue revision history is reversed")
        if self.status == "failed" and (self.attempts < 3 or not self.last_failure):
            raise ValueError("failed issue requires exhausted attempts and diagnosis")
        if self.status == "resolved" and self.last_failure and self.attempts >= 3:
            raise ValueError("exhausted issue cannot be silently resolved")
        if self.status == "accepted" and self.severity != "major":
            raise ValueError("blocker risk cannot be accepted")
        return self


class QualityPatchAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    baseline_revision: int = Field(ge=1)
    baseline_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["committed", "rejected"]
    reason: str | None = None
    candidate_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    input_bindings: tuple[str, ...] = ()


class QualityRiskAcceptance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    td_revision: int = Field(ge=1)
    td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    disclosure_location: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    disclosure_text: str = ""
    disclosure_label: str = ""


class QualityGateProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    td_revision: int = Field(ge=1)
    td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pack_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    obligations_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["continue", "diagnose", "final_audit", "ready"]
    blocking_issue_ids: tuple[str, ...] = ()


class QualityPatchRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    section_id: TdSectionId
    replacement_body: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    expected_td_revision: int = Field(ge=1, strict=True)
    expected_td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_review_revision: int = Field(ge=0, strict=True)


class QualityRiskAcceptanceRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    disclosure_location: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    expected_td_revision: int = Field(ge=1, strict=True)
    expected_td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class QualityCycleRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str = Field(min_length=1)
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    expected_td_revision: int = Field(ge=1, strict=True)
    expected_td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_review_revision: int = Field(ge=0, strict=True)
    max_steps: int = Field(default=3, ge=1, le=8, strict=True)


class QualityExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    provider_id: str
    td_revision: int
    td_content_hash: str
    input_bindings: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    steps: int = Field(ge=0, le=8)
    outcome: Literal["continue", "diagnose", "final_audit", "ready"]
    reason: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QualityAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    audit_id: str
    td_revision: int
    td_content_hash: str
    authority_pack_hash: str
    obligations_hash: str
    ledger_hash: str
    executor: str
    semantic_mode: Literal["human", "model"]
    passed: bool
    checks: tuple[str, ...]
    input_binding: str | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def quality_evidence_hash(*groups: tuple[BaseModel, ...]) -> str:
    import json
    from hashlib import sha256

    return sha256(
        json.dumps(
            [[item.model_dump(mode="json") for item in group] for group in groups],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class QualityIssueDecisionRequest(QualityCycleRequest):
    issue_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    user_confirmed: Literal[True]


class QualityIssueDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str
    command_id: str
    td_revision: int
    td_content_hash: str
    actor_claim: str
    rationale: str
    decision: Literal["dismissed_false_positive"] = "dismissed_false_positive"

"""Public technical authority, blueprint, revision, and approval contracts."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deliveryflow_contracts.governance import GovernanceWriteRequest
from deliveryflow_contracts.prd import PRODUCT_PRD_SECTION_IDS, PrdSectionId


class AuthorityTopic(StrEnum):
    API = "api"
    DATA = "data"
    ERROR = "error"
    IDEMPOTENCY = "idempotency"
    PERMISSION = "permission"
    STATE = "state"
    FAILURE = "failure"
    NON_FUNCTIONAL = "non_functional"


AUTHORITY_TOPICS = tuple(AuthorityTopic)


class AuthorityItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authority_id: str = Field(min_length=1)
    topic: AuthorityTopic
    statement: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    source_fact_ids: tuple[str, ...] = ()
    source_prd_section_ids: tuple[PrdSectionId, ...]

    @model_validator(mode="after")
    def validate_product_sources(self) -> "AuthorityItem":
        if not self.source_prd_section_ids or any(
            section_id not in PRODUCT_PRD_SECTION_IDS for section_id in self.source_prd_section_ids
        ):
            raise ValueError("Authority requires approved PRD product section sources")
        return self


class DesignAuthorityPack(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prd_revision: int = Field(ge=1)
    prd_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[AuthorityItem, ...]

    @model_validator(mode="after")
    def validate_topics(self) -> "DesignAuthorityPack":
        if tuple(item.topic for item in self.items) != AUTHORITY_TOPICS:
            raise ValueError("authority pack must contain every authority topic exactly once")
        if len({item.authority_id for item in self.items}) != len(self.items):
            raise ValueError("authority IDs must be unique")
        return self

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return sha256(payload).hexdigest()


class TdSectionId(StrEnum):
    DOCUMENT_INFO = "document_info"
    CONTEXT = "context"
    REPOSITORY_CONSTRAINTS = "repository_constraints"
    ARCHITECTURE_FLOW = "architecture_flow"
    CHANGE_SCOPE = "change_scope"
    DOMAIN_DATA_STATE = "domain_data_state"
    BACKEND = "backend"
    FRONTEND = "frontend"
    API_EVENTS_ERRORS = "api_events_errors"
    CONSISTENCY = "consistency"
    DEPENDENCIES = "dependencies"
    FAILURE_RECOVERY = "failure_recovery"
    PERFORMANCE_SECURITY_OBSERVABILITY = "performance_security_observability"
    TESTING_ACCEPTANCE = "testing_acceptance"
    RELEASE_RISK = "release_risk"
    TRACEABILITY = "traceability"


TD_SECTION_TITLES: dict[TdSectionId, str] = {
    TdSectionId.DOCUMENT_INFO: "文档信息",
    TdSectionId.CONTEXT: "背景、目标与技术范围",
    TdSectionId.REPOSITORY_CONSTRAINTS: "现状分析与仓库约束",
    TdSectionId.ARCHITECTURE_FLOW: "总体架构与端到端流程",
    TdSectionId.CHANGE_SCOPE: "模块边界与代码变更范围",
    TdSectionId.DOMAIN_DATA_STATE: "领域模型、数据模型与状态机",
    TdSectionId.BACKEND: "后端服务、持久化与异步流程",
    TdSectionId.FRONTEND: "前端页面、组件、交互与状态管理",
    TdSectionId.API_EVENTS_ERRORS: "API、事件与错误契约",
    TdSectionId.CONSISTENCY: "事务、幂等、并发与一致性",
    TdSectionId.DEPENDENCIES: "消息、缓存、文件与外部依赖",
    TdSectionId.FAILURE_RECOVERY: "失败恢复、补偿与降级",
    TdSectionId.PERFORMANCE_SECURITY_OBSERVABILITY: "性能、安全与可观测性",
    TdSectionId.TESTING_ACCEPTANCE: "测试与验收映射",
    TdSectionId.RELEASE_RISK: "发布、迁移、回滚与风险",
    TdSectionId.TRACEABILITY: "可追溯性",
}


class TdObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: str = Field(min_length=1)
    statement: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    prd_section_id: PrdSectionId
    prd_section_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_fact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_product_section(self) -> "TdObligation":
        if self.prd_section_id not in PRODUCT_PRD_SECTION_IDS:
            raise ValueError("TD obligation requires an approved PRD product section")
        return self


class TdSectionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: TdSectionId
    title: str = Field(min_length=1)
    authority_ids: tuple[str, ...] = ()
    obligation_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_title(self) -> "TdSectionPlan":
        if self.title != TD_SECTION_TITLES[self.section_id]:
            raise ValueError("section title must match the TD template")
        return self


class TdBlueprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prd_revision: int = Field(ge=1)
    prd_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_ids: tuple[str, ...]
    obligation_ids: tuple[str, ...]
    sections: tuple[TdSectionPlan, ...]

    @model_validator(mode="after")
    def validate_coverage(self) -> "TdBlueprint":
        if tuple(section.section_id for section in self.sections) != tuple(TdSectionId):
            raise ValueError("TD sections must follow the template order exactly")
        authority_refs = {
            authority_id for section in self.sections for authority_id in section.authority_ids
        }
        obligation_refs = {
            obligation_id for section in self.sections for obligation_id in section.obligation_ids
        }
        if authority_refs != set(self.authority_ids):
            raise ValueError("TD blueprint must cover every authority")
        if obligation_refs != set(self.obligation_ids):
            raise ValueError("TD blueprint must cover every PRD obligation")
        return self


class TdRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prd_revision: int = Field(ge=1)
    prd_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pack_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    obligations: tuple[TdObligation, ...]
    changed_section_id: TdSectionId | None = None
    feedback: str | None = Field(default=None, min_length=1, pattern=r"(?s).*\S.*")
    actor_claim: str | None = Field(default=None, min_length=1, pattern=r"(?s).*\S.*")
    command_id: str | None = Field(default=None, min_length=1, pattern=r"(?s).*\S.*")

    @model_validator(mode="after")
    def validate_content_hash(self) -> "TdRevision":
        if self.changed_section_id is not None and not all(
            (self.feedback, self.actor_claim, self.command_id)
        ):
            raise ValueError("TD section revision requires feedback, actor and command evidence")
        if sha256(self.content.encode()).hexdigest() != self.content_hash:
            raise ValueError("TD content hash must match the exact UTF-8 content")
        return self


class TdReadinessIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    section_id: TdSectionId | None = None


class TdReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    issues: tuple[TdReadinessIssue, ...] = ()

    ready: bool

    @model_validator(mode="after")
    def validate_ready(self) -> "TdReadiness":
        if self.ready != (not self.issues):
            raise ValueError("TD readiness must follow its structural issues")
        return self


class TdRevisionRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    section_id: TdSectionId
    replacement_body: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    feedback: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    expected_td_revision: int = Field(ge=1, strict=True)
    expected_td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_review_revision: int = Field(ge=0, strict=True)


class TdApprovalRequest(GovernanceWriteRequest):
    review_id: str = Field(min_length=1)
    expected_review_revision: int = Field(ge=0, strict=True)

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")


class TdApprovalReceipt(TdApprovalRequest):
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TechnicalDecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1)
    topic: AuthorityTopic
    question: str = Field(min_length=1)
    options: tuple[str, ...] = Field(min_length=2)
    reason: str = Field(min_length=1)


class TechnicalDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    actor: str = Field(min_length=1, pattern=r"(?s).*\S.*")


class SubmitTechnicalDecisionsRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_prd_revision: int = Field(ge=1)
    expected_prd_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decisions: tuple[TechnicalDecision, ...] = Field(min_length=1)


class TdReviewBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    prd_revision: int = Field(ge=1)
    prd_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    td_revision: int = Field(ge=1)
    td_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_pack_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    obligations_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class TdReviewExcerpt(BaseModel):
    """Exact half-open Unicode character interval in the complete Markdown document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    excerpt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_interval(self) -> "TdReviewExcerpt":
        if self.start >= self.end or self.end - self.start != len(self.excerpt):
            raise ValueError("review excerpt must match a nonempty character interval")
        return self


class TdReviewDisposition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(min_length=1)
    disposition: Literal["open", "confirmed_conflict", "dismissed", "product_change_required"]
    disposition_rationale: str | None = Field(default=None, min_length=1, pattern=r"(?s).*\S.*")

    @model_validator(mode="after")
    def validate_dismissal(self) -> "TdReviewDisposition":
        if self.disposition == "dismissed" and not self.disposition_rationale:
            raise ValueError("dismissal requires an explicit human rationale")
        return self


class TdReviewFinding(TdReviewDisposition):
    producer_kind: Literal["human", "model"]
    category: Literal["product_conflict", "uncertainty"]
    obligation_ids: tuple[str, ...] = Field(min_length=1)
    prd_excerpt: TdReviewExcerpt
    td_excerpt: TdReviewExcerpt
    reason: str = Field(min_length=1, pattern=r"(?s).*\S.*")


def td_review_conclusion(
    findings: tuple[TdReviewFinding, ...],
) -> Literal["no_conflict_observed", "changes_required", "product_change_required"]:
    blockers = [item for item in findings if item.disposition != "dismissed"]
    if any(item.disposition == "product_change_required" for item in blockers):
        return "product_change_required"
    return "changes_required" if blockers else "no_conflict_observed"


class TdReviewRecheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(min_length=1)
    outcome: Literal["fixed", "still_present", "not_applicable"]
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    td_excerpt: TdReviewExcerpt | None = None


class RecordTdReviewRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    expected_review_revision: int = Field(ge=0, strict=True)
    prior_review_id: str | None
    binding: TdReviewBinding
    producer_kind: Literal["human"]
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    user_confirmed: Literal[True]
    human_conclusion: Literal["no_conflict_observed", "changes_required", "product_change_required"]
    reviewed_obligation_ids: tuple[str, ...] = Field(min_length=1)
    findings: tuple[TdReviewFinding, ...] = ()
    existing_finding_dispositions: tuple[TdReviewDisposition, ...] = ()
    rechecks: tuple[TdReviewRecheck, ...] = ()

    @field_validator("user_confirmed", mode="before")
    @classmethod
    def require_explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("user_confirmed must be explicitly true")
        return value


class TdReviewRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str = Field(min_length=1)
    review_revision: int = Field(ge=1, strict=True)
    command_id: str = Field(min_length=1)
    binding: TdReviewBinding
    producer_kind: Literal["human"] = "human"
    user_confirmed: Literal[True] = True
    actor_claim: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    human_conclusion: Literal["no_conflict_observed", "changes_required", "product_change_required"]
    reviewed_obligation_ids: tuple[str, ...]
    findings: tuple[TdReviewFinding, ...]
    prior_review_id: str | None
    rechecks: tuple[TdReviewRecheck, ...] = ()
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    computed_status: Literal["blocked", "ready"]

    @model_validator(mode="after")
    def validate_evidence(self) -> "TdReviewRecord":
        if self.reviewed_at.utcoffset() is None:
            raise ValueError("human review time must include a timezone")
        if (
            len({item.finding_id for item in self.findings}) != len(self.findings)
            or len(set(self.reviewed_obligation_ids)) != len(self.reviewed_obligation_ids)
            or not self.reviewed_obligation_ids
            or self.prior_review_id == self.review_id
        ):
            raise ValueError("review evidence requires unique coverage and finding IDs")
        conclusion = td_review_conclusion(self.findings)
        if self.human_conclusion != conclusion or (
            self.computed_status == "ready" and conclusion != "no_conflict_observed"
        ):
            raise ValueError("review status and human conclusion must preserve finding blockers")
        return self


class TdReviewProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    binding: TdReviewBinding
    status: Literal["missing", "blocked", "ready", "stale"]
    current_review_id: str | None = None
    review_revision: int = Field(ge=0, strict=True)
    blocking_finding_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> "TdReviewProjection":
        if self.status == "missing":
            if (
                self.current_review_id is not None
                or self.review_revision
                or self.blocking_finding_ids
            ):
                raise ValueError("missing review cannot claim report evidence")
        elif self.status == "stale" and self.review_revision >= 1:
            pass
        elif not self.current_review_id or self.review_revision < 1:
            raise ValueError("review projection requires a current report ID and revision")
        if self.status == "ready" and self.blocking_finding_ids:
            raise ValueError("ready review cannot retain blocking findings")
        if len(set(self.blocking_finding_ids)) != len(self.blocking_finding_ids):
            raise ValueError("blocking finding IDs must be unique")
        return self


def td_obligations_hash(obligations: tuple[TdObligation, ...]) -> str:
    payload = json.dumps(
        [item.model_dump(mode="json") for item in obligations],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode()).hexdigest()

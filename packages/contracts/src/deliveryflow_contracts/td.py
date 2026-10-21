"""Public technical authority, blueprint, revision, and approval contracts."""

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.prd import PrdSectionId


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

    @model_validator(mode="after")
    def validate_content_hash(self) -> "TdRevision":
        if sha256(self.content.encode()).hexdigest() != self.content_hash:
            raise ValueError("TD content hash must match the exact UTF-8 content")
        return self


class TdApprovalRequest(BaseModel):
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


class SubmitTechnicalDecisionsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_prd_revision: int = Field(ge=1)
    expected_prd_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decisions: tuple[TechnicalDecision, ...] = Field(min_length=1)

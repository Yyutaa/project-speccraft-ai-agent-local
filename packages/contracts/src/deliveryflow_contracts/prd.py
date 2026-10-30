"""Public PRD planning, revision, readiness, and approval contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.governance import GovernanceWriteRequest
from deliveryflow_contracts.knowledge import Assumption, KnowledgeCitation


class PrdSectionId(StrEnum):
    DOCUMENT_INFO = "document_info"
    BACKGROUND = "background"
    SCOPE = "scope"
    ACTORS = "actors"
    JOURNEYS = "journeys"
    RULES = "rules"
    EXCEPTIONS = "exceptions"
    ACCEPTANCE = "acceptance"


PRODUCT_PRD_SECTION_IDS = (
    PrdSectionId.SCOPE,
    PrdSectionId.ACTORS,
    PrdSectionId.JOURNEYS,
    PrdSectionId.RULES,
    PrdSectionId.EXCEPTIONS,
    PrdSectionId.ACCEPTANCE,
)


class PrdSupportingContext(BaseModel):
    """Read-only review references, excluded from Author input and document hashes."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    knowledge_citations: tuple[KnowledgeCitation, ...] = ()
    assumptions: tuple[Assumption, ...] = ()


SECTION_TITLES: dict[PrdSectionId, str] = {
    PrdSectionId.DOCUMENT_INFO: "文档信息",
    PrdSectionId.BACKGROUND: "背景、目标与成功标准",
    PrdSectionId.SCOPE: "范围与非目标",
    PrdSectionId.ACTORS: "角色与场景",
    PrdSectionId.JOURNEYS: "功能与核心业务流程",
    PrdSectionId.RULES: "业务规则与产品边界",
    PrdSectionId.EXCEPTIONS: "异常体验与产品规则",
    PrdSectionId.ACCEPTANCE: "验收标准",
}


class PrdSectionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: PrdSectionId
    title: str = Field(min_length=1)
    applicable: bool
    fact_ids: tuple[str, ...] = ()
    applicability_reason: str | None = None

    @model_validator(mode="after")
    def validate_section(self) -> "PrdSectionPlan":
        if self.title != SECTION_TITLES[self.section_id]:
            raise ValueError("section title must match the PRD template")
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("section fact references must be unique")
        if not self.applicable and (self.fact_ids or not self.applicability_reason):
            raise ValueError("non-applicable section requires a reason and no fact references")
        return self


class PrdBlueprint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ledger_revision: int = Field(ge=1)
    authoritative_fact_ids: tuple[str, ...]
    sections: tuple[PrdSectionPlan, ...]

    @model_validator(mode="after")
    def validate_coverage(self) -> "PrdBlueprint":
        if tuple(section.section_id for section in self.sections) != tuple(PrdSectionId):
            raise ValueError("PRD sections must follow the template order exactly")
        if len(self.authoritative_fact_ids) != len(set(self.authoritative_fact_ids)):
            raise ValueError("authoritative fact IDs must be unique")
        references = {fact_id for section in self.sections for fact_id in section.fact_ids}
        authoritative = set(self.authoritative_fact_ids)
        if references - authoritative:
            raise ValueError("blueprint refers to a non-authoritative fact")
        if references != authoritative:
            raise ValueError("blueprint must cover every authoritative fact")
        return self


class PrdRevision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed_section_id: PrdSectionId | None = None
    feedback: str | None = None

    @model_validator(mode="after")
    def validate_content_hash(self) -> "PrdRevision":
        if sha256(self.content.encode("utf-8")).hexdigest() != self.content_hash:
            raise ValueError("PRD content hash must match the exact UTF-8 content")
        if self.changed_section_id is not None and not self.feedback:
            raise ValueError("a section revision requires feedback")
        return self


class PrdReadinessIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    section_id: PrdSectionId | None = None


class PrdReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    issues: tuple[PrdReadinessIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.issues


class PrdRevisionRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_revision: int = Field(ge=1)
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    section_id: PrdSectionId
    replacement_body: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    feedback: str = Field(min_length=1, pattern=r"(?s).*\S.*")


class PrdApprovalRequest(GovernanceWriteRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1, pattern=r"(?s).*\S.*")
    rationale: str = Field(min_length=1, pattern=r"(?s).*\S.*")


class PrdApprovalReceipt(PrdApprovalRequest):
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

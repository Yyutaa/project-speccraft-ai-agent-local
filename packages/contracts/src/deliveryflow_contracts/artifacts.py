"""Published artifact references and the machine-readable delivery contract."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.td import AuthorityTopic, TdSectionId


class ArtifactKind(StrEnum):
    PRD = "prd"
    TD = "td"
    DELIVERY_SPEC = "delivery_spec"


class ArtifactRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str = Field(min_length=1)
    kind: ArtifactKind
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1)


class ArtifactApprovalRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(min_length=1)
    approved_at: datetime


class ArtifactEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact: ArtifactRef
    derived_from: tuple[ArtifactRef, ...] = ()
    approval: ArtifactApprovalRef | None = None
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeliveryObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    obligation_id: str = Field(min_length=1)
    authority_topics: tuple[AuthorityTopic, ...]
    td_section_ids: tuple[TdSectionId, ...]

    @model_validator(mode="after")
    def require_traceability(self) -> "DeliveryObligation":
        if not self.authority_topics or not self.td_section_ids:
            raise ValueError("delivery obligation requires authority and TD traceability")
        return self


class DeliverySpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    run_id: str = Field(min_length=1)
    prd: ArtifactRef
    td: ArtifactRef
    authority_pack_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    obligations: tuple[DeliveryObligation, ...]

    @model_validator(mode="after")
    def validate_artifact_kinds(self) -> "DeliverySpec":
        if self.prd.kind is not ArtifactKind.PRD or self.td.kind is not ArtifactKind.TD:
            raise ValueError("DeliverySpec must reference approved PRD and TD artifacts")
        return self

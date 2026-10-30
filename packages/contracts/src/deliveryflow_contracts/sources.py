"""Strict server-owned source identity and explicit source admission contracts.

These models describe evidence and its use, not the semantic truth of submitted text.
SourceRecord must be constructed by a server capture boundary, never from client roles.
"""

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.context import SourceSnapshot, SourceType
from deliveryflow_contracts.dimensions import FactDimension

NonBlank = Annotated[str, Field(min_length=1, pattern=r"(?s).*\S.*")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MAX_CANDIDATE_BYTES = 64 * 1024
MAX_CANDIDATES = 32
GUIDE_PATHS = ("AGENTS.md", "README.md")
METADATA_PATHS = (".deliveryflow/repository.yaml", "package.json", "pyproject.toml")


class AdmissionModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")


class SourceRole(StrEnum):
    INLINE_REQUIREMENT = "inline_requirement"
    REQUIREMENT_FILE = "requirement_file"
    BUSINESS_KNOWLEDGE = "business_knowledge"
    REPOSITORY_GUIDE = "repository_guide"
    REPOSITORY_METADATA = "repository_metadata"

    @property
    def permits_product_claim(self) -> bool:
        return self in (self.INLINE_REQUIREMENT, self.REQUIREMENT_FILE)


def source_role_for_snapshot(snapshot: SourceSnapshot) -> SourceRole:
    """Derive a role from capture entry/path, never a file's declared source_type."""
    path = snapshot.normalized_path
    if path is None:
        if snapshot.source.source_type is not SourceType.INLINE_REQUIREMENT or (
            snapshot.source.path is not None
        ):
            raise ValueError("inline role requires the inline requirement entry")
        return SourceRole.INLINE_REQUIREMENT
    if snapshot.source.path != path:
        raise ValueError("source path must match its normalized capture path")
    parts = PurePosixPath(path).parts
    if path in GUIDE_PATHS:
        return SourceRole.REPOSITORY_GUIDE
    if path in METADATA_PATHS:
        return SourceRole.REPOSITORY_METADATA
    if len(parts) > 1 and parts[0] == "requirements" and path.lower().endswith(".md"):
        return SourceRole.REQUIREMENT_FILE
    if len(parts) > 1 and parts[0] == "knowledge":
        return SourceRole.BUSINESS_KNOWLEDGE
    raise ValueError("source path has no allowed server role")


class SourceRecord(AdmissionModel):
    source_id: NonBlank
    run_id: NonBlank
    repository_id: NonBlank | None = None
    source_role: SourceRole
    snapshot: SourceSnapshot

    @model_validator(mode="after")
    def validate_capture_binding(self) -> "SourceRecord":
        # SourceSnapshot predates instance revalidation: rebuild it to reject model_copy forgeries.
        snapshot = SourceSnapshot.model_validate(self.snapshot.model_dump())
        if self.source_role is not source_role_for_snapshot(snapshot):
            raise ValueError("source role must match the server capture entry and path")
        if (snapshot.normalized_path is not None) != (self.repository_id is not None):
            raise ValueError(
                "file sources require repository identity; inline sources cannot have it"
            )
        if len(snapshot.content.encode("utf-8")) > MAX_CANDIDATE_BYTES:
            raise ValueError("source exceeds the 64 KiB UTF-8 limit")
        return self


class RunSources(AdmissionModel):
    run_id: NonBlank
    records: tuple[SourceRecord, ...]

    @model_validator(mode="after")
    def validate_run_identity(self) -> "RunSources":
        if any(record.run_id != self.run_id for record in self.records):
            raise ValueError("all sources must belong to this Run")
        ids = [record.source_id for record in self.records]
        paths = [
            (record.repository_id, record.snapshot.normalized_path)
            for record in self.records
            if record.snapshot.normalized_path is not None
        ]
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
            raise ValueError("source identities and normalized repository paths must be unique")
        if sum(record.source_role is SourceRole.INLINE_REQUIREMENT for record in self.records) > 1:
            raise ValueError("a Run has at most one inline requirement entry")
        return self


class SourceClaimStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SourceClaimAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class SourceClaimUsage(StrEnum):
    PRODUCT = "product"
    BACKGROUND_ONLY = "background_only"


class PendingSourceClaim(AdmissionModel):
    candidate_id: NonBlank
    client_ref: NonBlank | None = None
    subject_key: NonBlank | None = None
    dimension: FactDimension | None = None
    rule_excerpt: NonBlank | None = None
    source_id: NonBlank
    source_sha256: Sha256
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    excerpt: NonBlank
    candidate_revision: int = Field(ge=1, strict=True)
    status: SourceClaimStatus = SourceClaimStatus.PENDING

    @model_validator(mode="after")
    def validate_interval(self) -> "PendingSourceClaim":
        if (self.subject_key is not None or self.rule_excerpt is not None) and (
            self.subject_key is None
            or self.dimension is None
            or self.rule_excerpt is None
            or self.rule_excerpt not in self.excerpt
        ):
            raise ValueError("candidate rule metadata requires an exact excerpt and dimension")
        if self.start >= self.end or self.end - self.start != len(self.excerpt):
            raise ValueError("candidate interval must describe the complete nonempty excerpt")
        if len(self.excerpt.encode("utf-8")) > MAX_CANDIDATE_BYTES:
            raise ValueError("candidate excerpt exceeds 64 KiB UTF-8")
        return self


class SourceClaimReview(AdmissionModel):
    review_id: NonBlank
    candidate_id: NonBlank
    candidate_revision: int = Field(ge=1, strict=True)
    source_id: NonBlank
    source_sha256: Sha256
    action: SourceClaimAction
    usage: SourceClaimUsage | None = None
    dimension: FactDimension | None = None

    @model_validator(mode="after")
    def validate_explicit_usage(self) -> "SourceClaimReview":
        if self.action is SourceClaimAction.REJECT:
            if self.usage is not None or self.dimension is not None:
                raise ValueError("rejection cannot assign a usage or dimension")
        elif self.usage is None or (
            (self.usage is SourceClaimUsage.PRODUCT) != (self.dimension is not None)
        ):
            raise ValueError(
                "accept requires product with one dimension or background_only without it"
            )
        return self


class SourceAdmissionCommand(AdmissionModel):
    run_id: NonBlank
    command_id: NonBlank
    batch_id: NonBlank
    batch_revision: int = Field(ge=1, strict=True)
    expected_revision: int = Field(ge=1, strict=True)
    actor_claim: NonBlank
    rationale: NonBlank
    confirmed_at: datetime
    user_confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_user_confirmation(self) -> "SourceAdmissionCommand":
        if self.user_confirmed is not True or self.confirmed_at.utcoffset() is None:
            raise ValueError("explicit user confirmation and a timezone-aware time are required")
        return self


class SourceAdmissionEvidence(SourceAdmissionCommand):
    review_id: NonBlank
    candidate_id: NonBlank
    candidate_revision: int = Field(ge=1, strict=True)
    source_id: NonBlank
    source_sha256: Sha256
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)
    excerpt: NonBlank
    action: SourceClaimAction
    usage: SourceClaimUsage | None = None
    dimension: FactDimension | None = None

    @model_validator(mode="after")
    def validate_candidate_and_review(self) -> "SourceAdmissionEvidence":
        PendingSourceClaim.model_validate(
            {
                key: getattr(self, key)
                for key in (
                    "candidate_id",
                    "candidate_revision",
                    "source_id",
                    "source_sha256",
                    "start",
                    "end",
                    "excerpt",
                )
            }
        )
        SourceClaimReview.model_validate(
            {
                key: getattr(self, key)
                for key in (
                    "review_id",
                    "candidate_id",
                    "candidate_revision",
                    "source_id",
                    "source_sha256",
                    "action",
                    "usage",
                    "dimension",
                )
            }
        )
        return self


class ClarificationResolution(AdmissionModel):
    question_id: NonBlank
    selected_option_id: NonBlank | None = None
    custom_answer: NonBlank | None = None
    confirmed_candidate_id: NonBlank | None = None

    @model_validator(mode="after")
    def validate_single_answer(self) -> "ClarificationResolution":
        if (
            sum(
                value is not None
                for value in (
                    self.selected_option_id,
                    self.custom_answer,
                    self.confirmed_candidate_id,
                )
            )
            != 1
        ):
            raise ValueError("provide exactly one option, explicit answer, or confirmed candidate")
        return self


def validate_source_claim_binding(
    run_sources: RunSources,
    candidate: PendingSourceClaim,
) -> SourceRecord:
    """Validate cross-object identity, product role, hash and exact Unicode interval."""
    source = next(
        (item for item in run_sources.records if item.source_id == candidate.source_id), None
    )
    if source is None or source.run_id != run_sources.run_id:
        raise ValueError("candidate source must belong to this Run")
    if not source.source_role.permits_product_claim:
        raise ValueError("only a product requirement source may supply a source claim")
    if candidate.source_sha256 != source.snapshot.sha256:
        raise ValueError("candidate SHA-256 must match its own source snapshot")
    if source.snapshot.content[candidate.start : candidate.end] != candidate.excerpt:
        raise ValueError("candidate must match its exact source interval")
    return source

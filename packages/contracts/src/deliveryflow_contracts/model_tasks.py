"""Data-only model task envelopes. No command, approval, or tool capability fields."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deliveryflow_contracts.facts import ClarificationProposal, GapSignal
from deliveryflow_contracts.prd import PrdBlueprint
from deliveryflow_contracts.sources import NonBlank, Sha256
from deliveryflow_contracts.td import (
    DesignAuthorityPack,
    TdBlueprint,
    TdObligation,
    TechnicalDecisionRequest,
)

MAX_MODEL_INPUT_BYTES = 128 * 1024
MAX_MODEL_OUTPUT_BYTES = 256 * 1024
MAX_MODEL_PROPOSALS = 32
TaskKind = Literal["prd_author", "td_author", "clarification", "review"]


class TaskData(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, revalidate_instances="always"
    )


class ModelResources(TaskData):
    template: str
    guide: str
    self_check: str


class ModelClaimRef(TaskData):
    claim_id: NonBlank
    content: NonBlank
    evidence_ids: tuple[NonBlank, ...] = Field(min_length=1)


class ModelContextEntry(TaskData):
    source_id: NonBlank
    source_role: Literal["repository_guide", "repository_metadata"]
    path: NonBlank
    sha256: Sha256
    selection_reason: NonBlank
    purpose: Literal["technical_constraint"] = "technical_constraint"
    content: str


class PrdTaskData(TaskData):
    blueprint: PrdBlueprint


class ModelTechnicalChoice(TaskData):
    request_id: NonBlank
    answer: NonBlank


class TdTaskData(TaskData):
    blueprint: TdBlueprint
    authority: DesignAuthorityPack
    obligations: tuple[TdObligation, ...]
    decisions: tuple[ModelTechnicalChoice, ...] = ()


class ClarificationTaskData(TaskData):
    gaps: tuple[GapSignal, ...]


class ReviewDocument(TaskData):
    document_id: NonBlank
    revision: int = Field(ge=1)
    content_hash: Sha256
    content: NonBlank


class ReviewTaskData(TaskData):
    left: ReviewDocument
    right: ReviewDocument


class ModelTaskInput(TaskData):
    task_kind: TaskKind
    instruction_version: NonBlank
    instruction_hash: Sha256
    system_rules: NonBlank
    resource_pack_version: NonBlank
    resource_pack_hash: Sha256
    resources: ModelResources
    input_binding: Sha256
    authoritative_claim_refs: tuple[ModelClaimRef, ...] = ()
    typed_context_entries: tuple[ModelContextEntry, ...] = ()
    payload: PrdTaskData | TdTaskData | ClarificationTaskData | ReviewTaskData


class ModelReviewFinding(TaskData):
    left_revision: int = Field(ge=1)
    left_content_hash: Sha256
    left_excerpt: NonBlank
    right_revision: int = Field(ge=1)
    right_content_hash: Sha256
    right_excerpt: NonBlank
    suggestion: NonBlank


class ModelTaskOutput(TaskData):
    task_kind: TaskKind
    input_binding: Sha256
    cited_ids: tuple[NonBlank, ...] = ()
    content: NonBlank | None = None
    obligations: tuple[TdObligation, ...] | None = None
    decision_requests: tuple[TechnicalDecisionRequest, ...] = Field(
        default=(), max_length=MAX_MODEL_PROPOSALS
    )
    proposals: tuple[ClarificationProposal, ...] = Field(default=(), max_length=MAX_MODEL_PROPOSALS)
    findings: tuple[ModelReviewFinding, ...] = Field(default=(), max_length=MAX_MODEL_PROPOSALS)

"""Public request and response models for the in-memory Run demonstration."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.artifacts import ArtifactEnvelope, ArtifactKind, DeliverySpec
from deliveryflow_contracts.context import (
    ContextMode,
    HarnessContextSlice,
    RepositoryBinding,
    SourceSnapshot,
)
from deliveryflow_contracts.facts import (
    ClarificationBatch,
    CompletenessResult,
    FactKind,
    FactLedger,
)
from deliveryflow_contracts.prd import (
    PrdApprovalReceipt,
    PrdBlueprint,
    PrdReadiness,
    PrdRevision,
)
from deliveryflow_contracts.td import (
    DesignAuthorityPack,
    TdApprovalReceipt,
    TdBlueprint,
    TdRevision,
    TechnicalDecision,
    TechnicalDecisionRequest,
)


class RunStatus(StrEnum):
    AWAITING_CLARIFICATION = "awaiting_clarification"
    PRD_AWAITING_APPROVAL = "prd_awaiting_approval"
    TD_AWAITING_DECISION = "td_awaiting_decision"
    TD_AWAITING_APPROVAL = "td_awaiting_approval"
    COMPLETED = "completed"


class AvailableCommand(StrEnum):
    SUBMIT_CLARIFICATION = "submit_clarification"
    REVISE_PRD = "revise_prd"
    APPROVE_PRD = "approve_prd"
    SUBMIT_TECHNICAL_DECISIONS = "submit_technical_decisions"
    APPROVE_TD = "approve_td"


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement: str | None = None
    requirement_path: str | None = Field(default=None, min_length=1)
    context_mode: ContextMode = ContextMode.INDEXED_READONLY

    @model_validator(mode="after")
    def require_one_requirement_source(self) -> "CreateRunRequest":
        has_inline = self.requirement is not None and bool(self.requirement.strip())
        has_file = self.requirement_path is not None and bool(self.requirement_path.strip())
        if has_inline == has_file:
            raise ValueError("provide exactly one nonblank requirement or requirement_path")
        return self


class RunResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    requirement: str = Field(min_length=1)
    status: RunStatus
    prd_blueprint: PrdBlueprint | None = None
    prd_revisions: tuple[PrdRevision, ...] = ()
    prd_draft: PrdRevision | None = None
    prd_readiness: PrdReadiness | None = None
    prd_approval: PrdApprovalReceipt | None = None
    design_authority: DesignAuthorityPack | None = None
    td_blueprint: TdBlueprint | None = None
    technical_decision_requests: tuple[TechnicalDecisionRequest, ...] = ()
    technical_decisions: tuple[TechnicalDecision, ...] = ()
    td_draft: TdRevision | None = None
    td_approval: TdApprovalReceipt | None = None
    delivery_spec: DeliverySpec | None = None
    artifact_envelopes: tuple[ArtifactEnvelope, ...] = ()
    available_commands: tuple[AvailableCommand, ...]
    source_snapshot: SourceSnapshot
    repository_binding: RepositoryBinding
    harness_context: HarnessContextSlice
    ledger: FactLedger
    completeness: CompletenessResult
    clarification_batch: ClarificationBatch | None = None

    @model_validator(mode="after")
    def validate_state_projection(self) -> "RunResponse":
        captured_sources = (
            self.source_snapshot,
            *(entry.snapshot for entry in self.harness_context.entries),
        )
        for fact in self.ledger.facts:
            if fact.kind is FactKind.FACT and fact.source is not None and not any(
                snapshot.sha256 == fact.source.sha256
                and fact.source.excerpt in snapshot.content
                for snapshot in captured_sources
            ):
                raise ValueError("source evidence must match a captured snapshot")

        if self.ledger.revision != self.completeness.ledger_revision:
            raise ValueError("completeness must describe the current Fact Ledger revision")

        if self.prd_draft is None:
            if (
                self.prd_blueprint is not None
                or self.prd_revisions
                or self.prd_readiness is not None
            ):
                raise ValueError("PRD planning and revision data require a PRD draft")
        else:
            if (
                self.prd_blueprint is None
                or self.prd_readiness is None
                or not self.prd_revisions
                or self.prd_revisions[-1] != self.prd_draft
                or tuple(revision.revision for revision in self.prd_revisions)
                != tuple(range(1, len(self.prd_revisions) + 1))
                or self.prd_blueprint.ledger_revision != self.ledger.revision
                or set(self.prd_blueprint.authoritative_fact_ids)
                != {fact.fact_id for fact in self.ledger.authoritative_facts}
                or self.prd_readiness.revision != self.prd_draft.revision
                or self.prd_readiness.content_hash != self.prd_draft.content_hash
            ):
                raise ValueError("PRD blueprint, revisions, readiness, and Ledger must agree")
        if self.prd_approval is not None and (
            self.prd_draft is None
            or self.prd_approval.revision != self.prd_draft.revision
            or self.prd_approval.content_hash != self.prd_draft.content_hash
            or self.prd_readiness is None
            or not self.prd_readiness.ready
        ):
            raise ValueError("PRD approval must freeze the ready current revision and hash")

        if self.prd_approval is None:
            if (
                self.design_authority is not None
                or self.td_blueprint is not None
                or self.technical_decision_requests
                or self.technical_decisions
                or self.td_draft is not None
                or self.td_approval is not None
                or self.delivery_spec is not None
                or self.artifact_envelopes
            ):
                raise ValueError("technical authority and artifacts require an approved PRD")
        elif (
            self.prd_draft is None
            or self.design_authority is None
            or self.td_blueprint is None
            or self.design_authority.prd_revision != self.prd_draft.revision
            or self.design_authority.prd_content_hash != self.prd_draft.content_hash
            or self.td_blueprint.prd_revision != self.prd_draft.revision
            or self.td_blueprint.prd_content_hash != self.prd_draft.content_hash
        ):
            raise ValueError("technical authority must bind the approved PRD")

        if self.td_draft is not None and (
            self.design_authority is None
            or self.prd_draft is None
            or self.td_draft.prd_revision != self.prd_draft.revision
            or self.td_draft.prd_content_hash != self.prd_draft.content_hash
            or self.td_draft.authority_pack_hash != self.design_authority.content_hash
        ):
            raise ValueError("TD draft must bind the approved PRD and authority pack")

        if self.status is RunStatus.AWAITING_CLARIFICATION:
            valid = (
                self.prd_draft is None
                and self.prd_blueprint is None
                and not self.prd_revisions
                and self.prd_approval is None
                and self.td_draft is None
                and self.td_approval is None
                and self.delivery_spec is None
                and not self.completeness.is_complete
                and self.clarification_batch is not None
                and self.clarification_batch.ledger_revision == self.ledger.revision
                and set(self.clarification_batch.blocking_gap_ids)
                == {gap.gap_id for gap in self.completeness.gaps if gap.blocking}
                and self.available_commands == (AvailableCommand.SUBMIT_CLARIFICATION,)
            )
        elif self.status is RunStatus.PRD_AWAITING_APPROVAL:
            valid = (
                self.prd_draft is not None
                and self.prd_approval is None
                and self.td_draft is None
                and self.td_approval is None
                and self.delivery_spec is None
                and self.completeness.is_complete
                and self.prd_readiness is not None
                and self.available_commands == (
                    (AvailableCommand.REVISE_PRD, AvailableCommand.APPROVE_PRD)
                    if self.prd_readiness.ready
                    else (AvailableCommand.REVISE_PRD,)
                )
            )
        elif self.status is RunStatus.TD_AWAITING_DECISION:
            valid = (
                self.prd_approval is not None
                and self.design_authority is not None
                and self.td_blueprint is not None
                and self.td_draft is None
                and self.td_approval is None
                and self.delivery_spec is None
                and bool(self.technical_decision_requests)
                and not self.technical_decisions
                and not self.artifact_envelopes
                and self.available_commands
                == (AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,)
            )
        elif self.status is RunStatus.TD_AWAITING_APPROVAL:
            valid = (
                self.prd_draft is not None
                and self.prd_approval is not None
                and self.prd_approval.revision == self.prd_draft.revision
                and self.prd_readiness is not None
                and self.prd_readiness.ready
                and self.td_draft is not None
                and self.td_approval is None
                and self.delivery_spec is None
                and not self.technical_decision_requests
                and not self.artifact_envelopes
                and self.completeness.is_complete
                and self.available_commands == (AvailableCommand.APPROVE_TD,)
            )
        else:
            valid = (
                self.prd_draft is not None
                and self.prd_approval is not None
                and self.prd_approval.revision == self.prd_draft.revision
                and self.prd_readiness is not None
                and self.prd_readiness.ready
                and self.td_draft is not None
                and self.td_approval is not None
                and self.td_approval.revision == self.td_draft.revision
                and self.delivery_spec is not None
                and len(self.artifact_envelopes) == 3
                and self.completeness.is_complete
                and self.available_commands == ()
            )

        if not valid:
            raise ValueError("Run status, approvals, artifacts, and commands are inconsistent")

        if self.delivery_spec is not None and (
            self.delivery_spec.run_id != self.run_id
            or self.prd_draft is None
            or self.delivery_spec.prd.revision != self.prd_draft.revision
            or self.delivery_spec.prd.content_hash != self.prd_draft.content_hash
            or self.td_draft is None
            or self.delivery_spec.td.revision != self.td_draft.revision
            or self.delivery_spec.td.content_hash != self.td_draft.content_hash
            or self.design_authority is None
            or self.delivery_spec.authority_pack_hash != self.design_authority.content_hash
            or {envelope.artifact.kind for envelope in self.artifact_envelopes}
            != {ArtifactKind.PRD, ArtifactKind.TD, ArtifactKind.DELIVERY_SPEC}
        ):
            raise ValueError("DeliverySpec must reference the approved Run artifacts")

        return self

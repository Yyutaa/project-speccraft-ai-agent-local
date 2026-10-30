"""Synchronous in-memory Run orchestration for the teaching scaffold."""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from uuid import uuid4

from deliveryflow_contracts.artifacts import (
    ArtifactApprovalRef,
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactRef,
    DeliveryObligation,
    DeliverySpec,
)
from deliveryflow_contracts.facts import (
    ClarificationBatch,
    ClarificationOption,
    ClarificationProposal,
    CompletenessResult,
    DecisionEvidence,
    FactDimension,
    FactKind,
    FactLedger,
    RequirementFact,
    SubmitClarificationRequest,
)
from deliveryflow_contracts.model_tasks import (
    ClarificationTaskData,
    ModelContextEntry,
    ModelTaskInput,
    ModelTaskOutput,
)
from deliveryflow_contracts.prd import (
    PrdApprovalReceipt,
    PrdApprovalRequest,
    PrdBlueprint,
    PrdReadiness,
    PrdRevision,
    PrdRevisionRequest,
    PrdSectionId,
    PrdSupportingContext,
)
from deliveryflow_contracts.runs import (
    AvailableCommand,
    CreateRunRequest,
    RunResponse,
    RunStatus,
)
from deliveryflow_contracts.sources import (
    RunSources,
    SourceAdmissionCommand,
    SourceClaimUsage,
)
from deliveryflow_contracts.td import (
    AuthorityTopic,
    DesignAuthorityPack,
    RecordTdReviewRequest,
    SubmitTechnicalDecisionsRequest,
    TdApprovalReceipt,
    TdApprovalRequest,
    TdBlueprint,
    TdObligation,
    TdReviewProjection,
    TdRevision,
    TdRevisionRequest,
)

from deliveryflow_speccraft.completeness import CompletenessAnalyzer
from deliveryflow_speccraft.knowledge_governance import (
    ContextGovernanceError,
    add_governance_gaps,
    capture_governance,
    resolve_governance,
)
from deliveryflow_speccraft.model_boundary import (
    build_clarification_task,
    build_prd_task,
    build_td_task,
    validate_task_input,
    validate_task_output,
)
from deliveryflow_speccraft.prd import (
    build_prd_blueprint,
    check_prd_readiness,
    replace_prd_section,
)
from deliveryflow_speccraft.prd_authoring import (
    FakePrdAuthor,
    PrdAuthor,
    load_prd_authoring_pack,
)
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.source_admission import (
    admit_source_claim,
    build_source_candidates,
    make_source_record,
)
from deliveryflow_speccraft.td import (
    build_design_authority,
    build_td_blueprint,
    check_td_readiness,
    extract_prd_obligations,
    replace_td_section,
    validate_td_obligations,
)
from deliveryflow_speccraft.td_authoring import (
    FakeTdAuthor,
    TdAuthor,
    load_td_authoring_pack,
)
from deliveryflow_speccraft.td_review import (
    current_td_review_binding,
    record_td_review,
    td_review_projection,
)


class RunNotFound(Exception):
    """Raised when a Run identifier is not present in this process."""


class InvalidRunTransition(Exception):
    """Raised when a command is not available in the current Run state."""


class RevisionConflict(Exception):
    """Raised when an approval refers to a different draft revision."""


class InvalidClarification(Exception):
    """Raised when an answer does not cover the current blocking questions."""


class DuplicateCommand(Exception):
    """Raised when an in-memory command identifier is submitted more than once."""


class ContentHashConflict(Exception):
    """Raised when a command names a different PRD content hash."""


class PrdNotReady(Exception):
    """Raised when structural PRD checks have unresolved issues."""


class InvalidPrdRevision(Exception):
    """Raised when a requested PRD edit escapes its target section."""


class TdObligationConflict(Exception):
    """Raised when a TD candidate changes a frozen product obligation."""


class InvalidTechnicalDecision(Exception):
    """Raised when technical decisions do not cover the current requests."""


class GovernanceError(Exception):
    """A stable public admission failure without exposing source content."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class FakeProvider:
    """Retains deterministic clarification proposals for the teaching flow."""

    def propose_clarifications(self, task: ModelTaskInput) -> ModelTaskOutput:
        task = validate_task_input(task)
        if not isinstance(task.payload, ClarificationTaskData):
            raise ValueError("clarification provider requires gap task")
        gaps = task.payload.gaps
        labels = {
            FactDimension.ROLE: "主要使用角色",
            FactDimension.WORKFLOW: "主要业务流程",
            FactDimension.PERMISSION: "权限规则",
            FactDimension.FAILURE: "失败时的处理方式",
            FactDimension.ACCEPTANCE: "验收标准",
        }
        choices = {
            FactDimension.ROLE: (("administrator", "管理员"), ("operator", "操作人员")),
            FactDimension.WORKFLOW: (("single_step", "单步骤流程"), ("multi_step", "多步骤流程")),
            FactDimension.PERMISSION: (
                ("role_based", "按角色限制"),
                ("all_users", "所有用户均可操作"),
            ),
            FactDimension.FAILURE: (
                ("stop_and_notify", "停止并提示错误"),
                ("allow_retry", "允许重试"),
            ),
            FactDimension.ACCEPTANCE: (
                ("testable", "使用可验证的验收条件"),
                ("user_review", "由用户确认结果"),
            ),
        }
        proposals = tuple(
            ClarificationProposal(
                question_id=gap.gap_id,
                gap_id=gap.gap_id,
                question=f"请明确{labels[gap.dimension]}。",
                options=tuple(
                    ClarificationOption(option_id=option_id, label=label)
                    for option_id, label in choices[gap.dimension]
                ),
                recommended_option_id=choices[gap.dimension][0][0],
                recommendation_reason="确定性示例建议，需由用户显式选择后才成为决定。",
            )
            for gap in gaps
            if gap.target_kind == "dimension" and gap.dimension is not None
        )
        proposals += tuple(
            ClarificationProposal(
                question_id=gap.gap_id,
                gap_id=gap.gap_id,
                question=gap.reason,
                target_kind=gap.target_kind,
                target_id=gap.target_id,
                object_revision=gap.object_revision,
                options=(
                    ClarificationOption(option_id="explicit_resolution", label="提交独立人工裁决"),
                ),
            )
            for gap in gaps
            if gap.target_kind != "dimension"
        )
        return validate_task_output(
            task,
            {
                "task_kind": "clarification",
                "input_binding": task.input_binding,
                "cited_ids": [item.gap_id for item in proposals],
                "proposals": [item.model_dump(mode="json") for item in proposals],
            },
        )


class InMemoryRunner:
    """Owns Run state for one API process; restarting the process clears it."""

    def __init__(
        self,
        harness: RepositoryHarness,
        prd_authoring_directory: Path,
        prd_author: PrdAuthor | None = None,
        td_authoring_directory: Path | None = None,
        td_author: TdAuthor | None = None,
    ) -> None:
        self._provider = FakeProvider()
        self._prd_author = prd_author or FakePrdAuthor()
        self._prd_pack = load_prd_authoring_pack(prd_authoring_directory)
        self._td_author = td_author or FakeTdAuthor()
        self._td_pack = load_td_authoring_pack(
            td_authoring_directory or prd_authoring_directory.parent / "td"
        )
        self._analyzer = CompletenessAnalyzer()
        self._harness = harness
        self._runs: dict[str, RunResponse] = {}
        self._used_command_ids: dict[str, set[str]] = {}
        self._lock = Lock()

    def create_run(self, request: CreateRunRequest) -> RunResponse:
        request = CreateRunRequest.model_validate(request.model_dump())
        if request.parent_run_id is not None:
            self.get_run(request.parent_run_id)
        context = self._harness.build(request)
        run_id = str(uuid4())
        snapshots = (context.requirement, *(entry.snapshot for entry in context.context.entries))
        records = tuple(
            make_source_record(
                run_id,
                snapshot,
                repository_id=context.binding.repository_id if snapshot.normalized_path else None,
            )
            for snapshot in snapshots
        )
        try:
            candidates = build_source_candidates(
                records[0],
                ranges=tuple((item.start, item.end) for item in request.claim_selections),
            )
        except ValueError as error:
            raise GovernanceError("invalid_source_claim", 422) from error
        try:
            records, candidates, citations, assumptions, conflicts = capture_governance(
                request, self._harness, records, candidates
            )
        except ValueError as error:
            code = (
                "knowledge_citation_invalid"
                if isinstance(error, ContextGovernanceError) and str(error).startswith("knowledge_")
                else "invalid_request"
            )
            raise GovernanceError(code, 422) from error
        ledger = FactLedger(revision=1, facts=())
        completeness = add_governance_gaps(self._analyzer.analyze(ledger), assumptions, conflicts)
        batch = self._make_batch(ledger, completeness, revision=1)
        batch = ClarificationBatch.model_validate(
            {
                **batch.model_dump(),
                "required_candidate_ids": tuple(item.candidate_id for item in candidates),
            }
        )
        run = RunResponse(
            run_id=run_id,
            parent_run_id=request.parent_run_id,
            requirement=context.requirement.content.strip(),
            status=RunStatus.AWAITING_CLARIFICATION,
            available_commands=(AvailableCommand.SUBMIT_CLARIFICATION,),
            source_snapshot=context.requirement,
            repository_binding=context.binding,
            harness_context=context.context,
            ledger=ledger,
            completeness=completeness,
            clarification_batch=batch,
            source_records=records,
            pending_source_claims=candidates,
            knowledge_citations=citations,
            assumptions=assumptions,
            context_conflicts=conflicts,
            prd_supporting_context=PrdSupportingContext(
                knowledge_citations=citations, assumptions=assumptions
            ),
        )
        with self._lock:
            self._runs[run_id] = run
            self._used_command_ids[run_id] = set()
        return run

    def submit_clarification(self, run_id: str, request: SubmitClarificationRequest) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            used_command_ids = self._used_command_ids[run_id]
            if request.command_id in used_command_ids:
                raise DuplicateCommand(request.command_id)
            if run.status is not RunStatus.AWAITING_CLARIFICATION:
                raise InvalidRunTransition("Run is not awaiting clarification")
            if request.expected_revision != run.ledger.revision:
                raise RevisionConflict("Fact Ledger revision does not match the current Run")
            batch = run.clarification_batch
            if batch is None:
                raise InvalidClarification("clarification batch is missing")

            if request.batch_id != batch.batch_id or request.batch_revision != batch.revision:
                raise GovernanceError("clarification_batch_conflict", 409)
            # Rebuild even direct model_copy callers at the domain trust boundary.
            request = SubmitClarificationRequest.model_validate(request.model_dump())
            proposals = {proposal.question_id: proposal for proposal in batch.proposals}
            blocking_question_ids = {
                proposal.question_id
                for proposal in batch.proposals
                if proposal.gap_id in batch.blocking_gap_ids
            }
            submitted_ids = (
                {item.question_id for item in request.answers}
                | {item.question_id for item in request.assumption_resolutions}
                | {item.question_id for item in request.context_conflict_resolutions}
            )
            optional_ids = {
                f"assumption-{item.assumption_id}"
                for item in run.assumptions
                if item.status == "pending" and not item.blocking
            }
            if submitted_ids - optional_ids != blocking_question_ids:
                raise InvalidClarification(
                    "answers must cover every blocking question exactly once"
                )
            reviews = {review.candidate_id: review for review in request.source_reviews}
            if set(reviews) != set(batch.required_candidate_ids):
                raise GovernanceError("source_review_required", 422)
            registry = RunSources(run_id=run_id, records=run.source_records)
            command = SourceAdmissionCommand(
                run_id=run_id,
                command_id=request.command_id,
                batch_id=batch.batch_id,
                batch_revision=batch.revision,
                expected_revision=request.expected_revision,
                actor_claim=request.actor_claim,
                rationale=request.rationale,
                confirmed_at=datetime.now(UTC),
                user_confirmed=request.user_confirmed,
            )
            admitted: dict[str, RequirementFact] = {}
            processed = []
            evidence = []
            for candidate in run.pending_source_claims:
                review = reviews[candidate.candidate_id]
                reviewed_source = next(
                    (record for record in registry.records if record.source_id == review.source_id),
                    None,
                )
                if reviewed_source is None or not reviewed_source.source_role.permits_product_claim:
                    raise GovernanceError("admission_forbidden_source", 403)
                if (
                    review.candidate_revision != candidate.candidate_revision
                    or review.source_id != candidate.source_id
                    or review.source_sha256 != candidate.source_sha256
                ):
                    raise GovernanceError("source_evidence_conflict", 409)
                try:
                    result = admit_source_claim(registry, candidate, review, command)
                except ValueError as error:
                    raise GovernanceError("invalid_source_claim", 422) from error
                processed.append(result.candidate)
                evidence.append(result.evidence)
                if result.fact is not None:
                    admitted[candidate.candidate_id] = result.fact
            gaps = {gap.gap_id: gap for gap in run.completeness.gaps}
            decisions: list[RequirementFact] = []
            decided_dimensions = set()
            for answer in request.answers:
                proposal = proposals.get(answer.question_id)
                if proposal is None or proposal.target_kind != "dimension":
                    raise InvalidClarification("answers must target a product dimension question")
                gap = gaps[proposal.gap_id]
                if answer.confirmed_candidate_id is not None:
                    fact = admitted.get(answer.confirmed_candidate_id)
                    if (
                        fact is None
                        or fact.dimension != gap.dimension
                        or (
                            fact.admission_evidence is None
                            or fact.admission_evidence.usage is not SourceClaimUsage.PRODUCT
                        )
                    ):
                        raise InvalidClarification(
                            "candidate must be accepted for this product dimension"
                        )
                    continue
                if gap.dimension in decided_dimensions:
                    raise InvalidClarification(
                        "one final explicit decision is allowed per dimension"
                    )
                decided_dimensions.add(gap.dimension)
                if answer.selected_option_id is not None:
                    option = next(
                        (
                            option
                            for option in proposal.options
                            if option.option_id == answer.selected_option_id
                        ),
                        None,
                    )
                    if option is None:
                        raise InvalidClarification("selected option is not part of the question")
                    claim = option.label
                else:
                    claim = (answer.custom_answer or "").strip()
                decisions.append(
                    RequirementFact(
                        fact_id=f"decision-{batch.revision}-{answer.question_id}",
                        kind=FactKind.DECISION,
                        dimension=gap.dimension,
                        claim=claim,
                        decision_evidence=DecisionEvidence(
                            batch_id=batch.batch_id,
                            question_id=answer.question_id,
                            command_id=request.command_id,
                            expected_revision=request.expected_revision,
                            answer=claim,
                            actor_claim=request.actor_claim,
                            rationale=request.rationale,
                        ),
                    )
                )
            ledger = FactLedger(
                revision=run.ledger.revision + 1,
                facts=run.ledger.facts + tuple(admitted.values()) + tuple(decisions),
            )
            try:
                governance_update = resolve_governance(run, request, tuple(decisions), ledger)
            except ContextGovernanceError as error:
                reason = str(error)
                if "revision_conflict" in reason:
                    raise GovernanceError("revision_conflict", 409) from error
                code = (
                    "assumption_resolution_invalid"
                    if reason.startswith("assumption_") or reason == "unexpected_context_answer"
                    else "context_conflict_invalid"
                )
                raise GovernanceError(code, 422) from error
            candidate_ledger = governance_update["ledger"]
            assert isinstance(candidate_ledger, FactLedger)
            ledger = candidate_ledger
            assumptions = governance_update["assumptions"]
            conflicts = governance_update["context_conflicts"]
            assert isinstance(assumptions, tuple) and isinstance(conflicts, tuple)
            completeness = add_governance_gaps(
                self._analyzer.analyze(ledger), assumptions, conflicts
            )
            if not completeness.is_complete:
                raise GovernanceError("clarification_unresolved", 409)
            blueprint, prd, readiness = self._create_prd(ledger)
            updated = self._validated_update(
                run,
                {
                    **governance_update,
                    "ledger": ledger,
                    "completeness": completeness,
                    "pending_source_claims": tuple(processed),
                    "source_admission_evidence": tuple(evidence),
                    "status": RunStatus.PRD_AWAITING_APPROVAL,
                    "prd_blueprint": blueprint,
                    "prd_draft": prd,
                    "prd_revisions": (prd,),
                    "prd_readiness": readiness,
                    "available_commands": self._prd_commands(readiness),
                },
            )

            self._runs[run_id] = updated
            used_command_ids.add(request.command_id)
            return updated

    def get_run(self, run_id: str) -> RunResponse:
        with self._lock:
            return self._require_run(run_id)

    def discard_unpublished_run(self, run_id: str) -> None:
        """Compensate a failed workflow start before CreateRun is returned."""
        with self._lock:
            self._runs.pop(run_id, None)
            self._used_command_ids.pop(run_id, None)

    def revise_prd(self, run_id: str, request: PrdRevisionRequest) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            if run.status is not RunStatus.PRD_AWAITING_APPROVAL or run.prd_draft is None:
                raise InvalidRunTransition("PRD is frozen or has not been created")
            if request.expected_revision != run.prd_draft.revision:
                raise RevisionConflict("PRD revision does not match the current draft")
            if request.expected_content_hash != run.prd_draft.content_hash:
                raise ContentHashConflict("PRD hash does not match the current draft")
            try:
                content = replace_prd_section(
                    run.prd_draft.content, request.section_id, request.replacement_body
                )
            except ValueError as error:
                raise InvalidPrdRevision(str(error)) from error
            revision = PrdRevision(
                revision=run.prd_draft.revision + 1,
                content=content,
                content_hash=sha256(content.encode("utf-8")).hexdigest(),
                changed_section_id=request.section_id,
                feedback=request.feedback.strip(),
            )
            readiness = check_prd_readiness(revision)
            updated = self._validated_update(
                run,
                {
                    "prd_draft": revision,
                    "prd_revisions": run.prd_revisions + (revision,),
                    "prd_readiness": readiness,
                    "available_commands": self._prd_commands(readiness),
                },
            )
            self._runs[run_id] = updated
            return updated

    def approve_prd(self, run_id: str, request: PrdApprovalRequest) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            if run.status is not RunStatus.PRD_AWAITING_APPROVAL:
                raise InvalidRunTransition("PRD is not awaiting approval")
            if run.prd_draft is None:
                raise InvalidRunTransition("PRD draft is missing")
            if request.revision != run.prd_draft.revision:
                raise RevisionConflict("PRD revision does not match the current draft")
            if request.content_hash != run.prd_draft.content_hash:
                raise ContentHashConflict("PRD hash does not match the current draft")
            if run.prd_readiness is None or not run.prd_readiness.ready:
                raise PrdNotReady("PRD has unresolved structural issues")

            if run.prd_blueprint is None:
                raise InvalidRunTransition("PRD blueprint is missing")
            receipt = PrdApprovalReceipt(**request.model_dump())
            authority = build_design_authority(run.prd_draft, receipt, run.prd_blueprint)
            obligations = extract_prd_obligations(run.prd_draft, run.prd_blueprint)
            blueprint = build_td_blueprint(authority, obligations)
            task = build_td_task(
                blueprint,
                authority,
                obligations,
                self._td_pack,
                self._repository_constraints(run),
                (),
            )
            result = validate_task_output(task, self._td_author.author(task))
            if result.decision_requests:
                update: dict[str, object] = {
                    "status": RunStatus.TD_AWAITING_DECISION,
                    "prd_approval": receipt,
                    "design_authority": authority,
                    "td_blueprint": blueprint,
                    "technical_decision_requests": result.decision_requests,
                    "available_commands": (AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,),
                }
            else:
                td = self._make_td_revision(
                    run,
                    receipt,
                    authority,
                    blueprint,
                    obligations,
                    result.content,
                    result.obligations,
                )
                update = {
                    "status": RunStatus.TD_AWAITING_APPROVAL,
                    "prd_approval": receipt,
                    "design_authority": authority,
                    "td_blueprint": blueprint,
                    "td_draft": td,
                    "available_commands": (
                        AvailableCommand.RECORD_TD_REVIEW,
                        AvailableCommand.REVISE_TD,
                    ),
                }
            updated = self._validated_update(run, update)
            self._runs[run_id] = updated
            return updated

    def submit_technical_decisions(
        self, run_id: str, request: SubmitTechnicalDecisionsRequest
    ) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            if run.status is not RunStatus.TD_AWAITING_DECISION:
                raise InvalidRunTransition("Run is not awaiting technical decisions")
            if run.prd_draft is None or run.prd_approval is None or run.prd_blueprint is None:
                raise InvalidRunTransition("approved PRD is missing")
            if request.expected_prd_revision != run.prd_draft.revision:
                raise RevisionConflict("PRD revision does not match")
            if request.expected_prd_content_hash != run.prd_draft.content_hash:
                raise ContentHashConflict("PRD hash does not match")
            requests = {item.request_id: item for item in run.technical_decision_requests}
            decisions = {item.request_id: item for item in request.decisions}
            if set(decisions) != set(requests) or any(
                item.answer not in requests[item.request_id].options for item in request.decisions
            ):
                raise InvalidTechnicalDecision(
                    "answers must cover each request with an offered option"
                )
            if run.design_authority is None or run.td_blueprint is None:
                raise InvalidRunTransition("technical authority is missing")
            obligations = extract_prd_obligations(run.prd_draft, run.prd_blueprint)
            task = build_td_task(
                run.td_blueprint,
                run.design_authority,
                obligations,
                self._td_pack,
                self._repository_constraints(run),
                request.decisions,
            )
            result = validate_task_output(task, self._td_author.author(task))
            if result.decision_requests or result.content is None:
                raise InvalidTechnicalDecision("technical decisions did not resolve TD input")
            td = self._make_td_revision(
                run,
                run.prd_approval,
                run.design_authority,
                run.td_blueprint,
                obligations,
                result.content,
                result.obligations,
            )
            updated = self._validated_update(
                run,
                {
                    "status": RunStatus.TD_AWAITING_APPROVAL,
                    "technical_decision_requests": (),
                    "technical_decisions": request.decisions,
                    "td_draft": td,
                    "available_commands": (
                        AvailableCommand.RECORD_TD_REVIEW,
                        AvailableCommand.REVISE_TD,
                    ),
                },
            )
            self._runs[run_id] = updated
            return updated

    def revise_td(self, run_id: str, request: TdRevisionRequest) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            if run.status is not RunStatus.TD_AWAITING_APPROVAL or run.td_draft is None:
                raise InvalidRunTransition("TD is frozen or has not been created")
            try:
                request = TdRevisionRequest.model_validate(request.model_dump())
            except ValueError as error:
                raise GovernanceError("invalid_td_revision", 422) from error
            if request.command_id in self._used_command_ids[run_id]:
                raise DuplicateCommand(request.command_id)
            if request.expected_td_revision != run.td_draft.revision:
                raise RevisionConflict("TD revision_conflict")
            if request.expected_td_content_hash != run.td_draft.content_hash:
                raise ContentHashConflict("TD content_hash_conflict")
            if (
                run.td_review is None
                or request.expected_review_revision != run.td_review.review_revision
            ):
                raise GovernanceError("td_review_conflict", 409)
            try:
                content = replace_td_section(
                    run.td_draft.content, request.section_id, request.replacement_body
                )
                revision = TdRevision.model_validate(
                    run.td_draft.model_dump()
                    | {
                        "revision": run.td_draft.revision + 1,
                        "content": content,
                        "content_hash": sha256(content.encode()).hexdigest(),
                        "changed_section_id": request.section_id,
                        "feedback": request.feedback,
                        "actor_claim": request.actor_claim,
                        "command_id": request.command_id,
                    }
                )
                assert run.prd_draft and run.prd_approval and run.design_authority
                assert run.prd_blueprint and run.td_blueprint
                validate_td_obligations(
                    revision,
                    run.prd_draft,
                    run.prd_approval,
                    run.design_authority,
                    run.td_blueprint,
                    extract_prd_obligations(run.prd_draft, run.prd_blueprint),
                )
            except ValueError as error:
                raise GovernanceError("invalid_td_revision", 422) from error
            staged = run.model_copy(update={"td_draft": revision})
            projection = run.td_review.model_copy(
                update={
                    "binding": current_td_review_binding(staged),
                    "status": "stale",
                    "review_revision": run.td_review.review_revision + 1,
                }
            )
            updated = self._validated_update(
                run,
                {
                    "td_draft": revision,
                    "td_revisions": (*run.td_revisions, revision),
                    "td_readiness": check_td_readiness(revision),
                    "td_review": projection,
                    "available_commands": (
                        AvailableCommand.RECORD_TD_REVIEW,
                        AvailableCommand.REVISE_TD,
                    ),
                },
            )
            self._runs[run_id] = updated
            self._used_command_ids[run_id].add(request.command_id)
            return updated

    def record_td_review(self, run_id: str, request: RecordTdReviewRequest) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            if run.status is not RunStatus.TD_AWAITING_APPROVAL:
                raise InvalidRunTransition("TD is not awaiting review")
            if request.command_id in self._used_command_ids[run_id]:
                raise DuplicateCommand(request.command_id)
            try:
                request = RecordTdReviewRequest.model_validate(request.model_dump())
            except ValueError as error:
                raise GovernanceError("invalid_td_review", 422) from error
            try:
                binding = current_td_review_binding(run)
            except ValueError as error:
                raise GovernanceError("td_review_conflict", 409) from error
            if (
                run.td_review is None
                or request.binding != binding
                or request.expected_review_revision != run.td_review.review_revision
                or request.prior_review_id != run.td_review.current_review_id
            ):
                raise GovernanceError("td_review_conflict", 409)
            try:
                record = record_td_review(run, request)
            except ValueError as error:
                raise GovernanceError("invalid_td_review", 422) from error
            projection = td_review_projection(binding, record)
            commands: tuple[AvailableCommand, ...] = (
                AvailableCommand.RECORD_TD_REVIEW,
                AvailableCommand.REVISE_TD,
            )
            if projection.status == "ready":
                commands += (AvailableCommand.APPROVE_TD,)
            updated = self._validated_update(
                run,
                {
                    "td_review_records": (*run.td_review_records, record),
                    "td_review": projection,
                    "available_commands": commands,
                },
            )
            self._runs[run_id] = updated
            self._used_command_ids[run_id].add(request.command_id)
            return updated

    def approve_td(self, run_id: str, request: TdApprovalRequest) -> RunResponse:
        with self._lock:
            run = self._require_run(run_id)
            if run.status is not RunStatus.TD_AWAITING_APPROVAL:
                raise InvalidRunTransition("TD is not awaiting approval")
            if run.prd_draft is None or run.prd_blueprint is None:
                raise InvalidRunTransition("PRD draft is missing")
            if run.td_draft is None:
                raise InvalidRunTransition("TD draft is missing")
            if request.revision != run.td_draft.revision:
                raise RevisionConflict("TD revision does not match the current draft")
            if request.content_hash != run.td_draft.content_hash:
                raise ContentHashConflict("TD hash does not match the current draft")
            if run.prd_approval is None:
                raise InvalidRunTransition("PRD has not been approved")
            if run.design_authority is None or run.td_blueprint is None:
                raise InvalidRunTransition("technical authority is missing")
            expected_obligations = extract_prd_obligations(run.prd_draft, run.prd_blueprint)
            try:
                validate_td_obligations(
                    run.td_draft,
                    run.prd_draft,
                    run.prd_approval,
                    run.design_authority,
                    run.td_blueprint,
                    expected_obligations,
                )
            except ValueError as error:
                raise TdObligationConflict(str(error)) from error
            review = run.td_review
            if review is None or review.status == "missing":
                raise GovernanceError("td_review_required", 409)
            if (request.review_id != review.current_review_id
                or request.expected_review_revision != review.review_revision
                or review.binding != current_td_review_binding(run)
                or not run.td_review_records
                or run.td_review_records[-1].binding != review.binding
            ):
                raise GovernanceError("td_review_conflict", 409)
            if review.status != "ready":
                raise GovernanceError("td_review_blocked", 409)
            if not check_td_readiness(run.td_draft).ready:
                raise GovernanceError("td_review_blocked", 409)
            receipt = TdApprovalReceipt(**request.model_dump())
            delivery_spec, envelopes = self._publish(run, expected_obligations, receipt)
            updated = self._validated_update(
                run,
                {
                    "status": RunStatus.COMPLETED,
                    "td_approval": receipt,
                    "delivery_spec": delivery_spec,
                    "artifact_envelopes": envelopes,
                    "available_commands": (),
                },
            )
            self._runs[run_id] = updated
            return updated

    def _make_td_revision(
        self,
        run: RunResponse,
        approval: PrdApprovalReceipt,
        authority: DesignAuthorityPack,
        blueprint: TdBlueprint,
        expected_obligations: tuple[TdObligation, ...],
        content: str | None,
        proposed_obligations: tuple[TdObligation, ...] | None,
    ) -> TdRevision:
        if run.prd_draft is None or content is None or proposed_obligations is None:
            raise InvalidRunTransition("TD author did not return a complete candidate")
        td = TdRevision(
            revision=1,
            content=content,
            content_hash=sha256(content.encode()).hexdigest(),
            prd_revision=run.prd_draft.revision,
            prd_content_hash=run.prd_draft.content_hash,
            authority_pack_hash=authority.content_hash,
            obligations=proposed_obligations,
        )
        try:
            validate_td_obligations(
                td,
                run.prd_draft,
                approval,
                authority,
                blueprint,
                expected_obligations,
            )
        except ValueError as error:
            raise TdObligationConflict(str(error)) from error
        return td

    @staticmethod
    def _repository_constraints(run: RunResponse) -> tuple[ModelContextEntry, ...]:
        records = {record.snapshot.normalized_path: record for record in run.source_records}
        return tuple(
            ModelContextEntry.model_validate(
                {
                    "source_id": records[entry.snapshot.normalized_path].source_id,
                    "source_role": records[entry.snapshot.normalized_path].source_role.value,
                    "path": entry.snapshot.normalized_path,
                    "sha256": entry.snapshot.sha256,
                    "selection_reason": entry.selection_reason,
                    "content": entry.snapshot.content,
                }
            )
            for entry in run.harness_context.entries
        )

    @staticmethod
    def _publish(
        run: RunResponse,
        obligations: tuple[TdObligation, ...],
        td_approval: TdApprovalReceipt,
    ) -> tuple[DeliverySpec, tuple[ArtifactEnvelope, ...]]:
        if (
            run.prd_draft is None
            or run.td_draft is None
            or run.design_authority is None
            or run.td_blueprint is None
        ):
            raise InvalidRunTransition("approved artifacts are missing")
        prd_ref = ArtifactRef(
            artifact_id=f"{run.run_id}:prd",
            kind=ArtifactKind.PRD,
            revision=run.prd_draft.revision,
            content_hash=run.prd_draft.content_hash,
            media_type="text/markdown",
        )
        td_ref = ArtifactRef(
            artifact_id=f"{run.run_id}:td",
            kind=ArtifactKind.TD,
            revision=run.td_draft.revision,
            content_hash=run.td_draft.content_hash,
            media_type="text/markdown",
        )
        topic_by_section = {
            PrdSectionId.SCOPE: (AuthorityTopic.DATA, AuthorityTopic.NON_FUNCTIONAL),
            PrdSectionId.ACTORS: (AuthorityTopic.PERMISSION,),
            PrdSectionId.JOURNEYS: (AuthorityTopic.API, AuthorityTopic.STATE),
            PrdSectionId.RULES: (AuthorityTopic.PERMISSION, AuthorityTopic.IDEMPOTENCY),
            PrdSectionId.EXCEPTIONS: (AuthorityTopic.ERROR, AuthorityTopic.FAILURE),
            PrdSectionId.ACCEPTANCE: (AuthorityTopic.NON_FUNCTIONAL,),
        }
        delivery_obligations = tuple(
            DeliveryObligation(
                obligation_id=obligation.obligation_id,
                authority_topics=topic_by_section[obligation.prd_section_id],
                td_section_ids=tuple(
                    section.section_id
                    for section in run.td_blueprint.sections
                    if obligation.obligation_id in section.obligation_ids
                ),
            )
            for obligation in obligations
        )
        spec = DeliverySpec(
            schema_version="1.0",
            run_id=run.run_id,
            prd=prd_ref,
            td=td_ref,
            authority_pack_hash=run.design_authority.content_hash,
            obligations=delivery_obligations,
        )
        spec_ref = ArtifactRef(
            artifact_id=f"{run.run_id}:delivery-spec",
            kind=ArtifactKind.DELIVERY_SPEC,
            revision=1,
            content_hash=sha256(spec.model_dump_json().encode()).hexdigest(),
            media_type="application/json",
        )
        if run.prd_approval is None:
            raise InvalidRunTransition("PRD approval is missing")
        prd_approval = ArtifactApprovalRef(
            revision=run.prd_approval.revision,
            content_hash=run.prd_approval.content_hash,
            actor=run.prd_approval.actor,
            approved_at=run.prd_approval.approved_at,
        )
        td_approval_ref = ArtifactApprovalRef(
            revision=td_approval.revision,
            content_hash=td_approval.content_hash,
            actor=td_approval.actor,
            approved_at=td_approval.approved_at,
        )
        return spec, (
            ArtifactEnvelope(artifact=prd_ref, approval=prd_approval),
            ArtifactEnvelope(artifact=td_ref, derived_from=(prd_ref,), approval=td_approval_ref),
            ArtifactEnvelope(
                artifact=spec_ref,
                derived_from=(prd_ref, td_ref),
                approval=td_approval_ref,
            ),
        )

    def _require_run(self, run_id: str) -> RunResponse:
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise RunNotFound(run_id) from error

    def _create_prd(self, ledger: FactLedger) -> tuple[PrdBlueprint, PrdRevision, PrdReadiness]:
        blueprint = build_prd_blueprint(ledger)
        evidence_refs: dict[str, tuple[str, ...]] = {}
        for fact in ledger.authoritative_facts:
            if fact.admission_evidence is not None:
                evidence = fact.admission_evidence
                evidence_refs[fact.fact_id] = (
                    f"source:{evidence.source_id}:sha256:{evidence.source_sha256}",
                    f"candidate:{evidence.candidate_id}:r{evidence.candidate_revision}",
                    f"excerpt-sha256:{sha256(evidence.excerpt.encode()).hexdigest()}",
                )
            elif fact.decision_evidence is not None:
                decision = fact.decision_evidence
                evidence_refs[fact.fact_id] = (
                    f"command:{decision.command_id}:batch:{decision.batch_id}",
                    f"question:{decision.question_id}:ledger-r{decision.expected_revision}",
                )
        task = build_prd_task(
            blueprint,
            {fact.fact_id: fact.claim for fact in ledger.authoritative_facts},
            self._prd_pack,
            evidence_refs=evidence_refs,
        )
        result = validate_task_output(task, self._prd_author.author(task))
        assert result.content is not None
        content = result.content
        revision = PrdRevision(
            revision=1,
            content=content,
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
        )
        return blueprint, revision, check_prd_readiness(revision)

    @staticmethod
    def _prd_commands(readiness: PrdReadiness | None) -> tuple[AvailableCommand, ...]:
        return (
            (AvailableCommand.REVISE_PRD, AvailableCommand.APPROVE_PRD)
            if readiness is not None and readiness.ready
            else (AvailableCommand.REVISE_PRD,)
        )

    @staticmethod
    def _validated_update(run: RunResponse, update: dict[str, object]) -> RunResponse:
        updated = run.model_copy(update=update)
        if updated.td_draft is not None:
            updated = updated.model_copy(update={
                "td_revisions": updated.td_revisions or (updated.td_draft,),
                "td_readiness": check_td_readiness(updated.td_draft),
            })
        if updated.td_draft is not None and updated.td_review is None:
            updated = updated.model_copy(update={"td_review": TdReviewProjection(
                binding=current_td_review_binding(updated), status="missing", review_revision=0,
            )})
        return RunResponse.model_validate(
            {
                **updated.model_dump(),
                "prd_supporting_context": PrdSupportingContext(
                    knowledge_citations=updated.knowledge_citations, assumptions=updated.assumptions
                ),
            }
        )

    def _make_batch(
        self,
        ledger: FactLedger,
        completeness: CompletenessResult,
        revision: int,
    ) -> ClarificationBatch:
        task = build_clarification_task(completeness.gaps)
        proposals = validate_task_output(
            task, self._provider.propose_clarifications(task)
        ).proposals
        gaps = tuple(gap.gap_id for gap in completeness.gaps)
        blocking = tuple(gap.gap_id for gap in completeness.gaps if gap.blocking)
        return ClarificationBatch(
            batch_id=str(uuid4()),
            revision=revision,
            ledger_revision=ledger.revision,
            gap_ids=gaps,
            blocking_gap_ids=blocking,
            proposals=proposals,
        )

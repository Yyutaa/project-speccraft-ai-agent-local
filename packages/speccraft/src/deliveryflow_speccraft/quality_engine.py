"""Bounded semantic quality orchestration; candidates never grant human approvals."""

import json
from hashlib import sha256
from typing import Literal, Protocol
from uuid import uuid4

from deliveryflow_contracts.model_tasks import (
    ModelResources,
    ModelTaskInput,
    ModelTaskOutput,
    ModelTechnicalChoice,
    QualityTaskData,
    ReviewDocument,
)
from deliveryflow_contracts.quality import (
    QualityAudit,
    QualityCycleRequest,
    QualityExecution,
    QualityIssueRecord,
    QualityPatchAttempt,
    quality_evidence_hash,
)
from deliveryflow_contracts.runs import RunResponse
from deliveryflow_contracts.td import TD_SECTION_TITLES, TdRevision

from deliveryflow_speccraft.model_boundary import (
    ModelBoundaryError,
    build_task,
    validate_task_output,
)
from deliveryflow_speccraft.td import (
    check_td_readiness,
    extract_prd_obligations,
    validate_td_obligations,
)
from deliveryflow_speccraft.td_quality import apply_quality_patch, project_quality
from deliveryflow_speccraft.td_review import current_td_review_binding


class QualityModel(Protocol):
    @property
    def identity(self) -> str: ...

    def execute(self, task: ModelTaskInput) -> object: ...


class QualityProviderError(RuntimeError):
    """Only stable sanitized codes cross the adapter boundary."""

    def __init__(self, code: str = "quality_provider_unavailable") -> None:
        self.code = code
        super().__init__(code)


def digest(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ledger_hash(run: RunResponse) -> str:
    return quality_evidence_hash(
        run.quality_issues,
        run.quality_risk_acceptances,
        run.quality_patch_attempts,
        run.quality_executions,
        run.quality_issue_decisions,
    )


def audit_current(run: RunResponse) -> bool:
    td = run.td_draft
    return bool(
        td
        and any(
            a.passed
            and a.td_revision == td.revision
            and a.td_content_hash == td.content_hash
            and a.authority_pack_hash == td.authority_pack_hash
            and a.obligations_hash == digest([i.model_dump(mode="json") for i in td.obligations])
            and a.ledger_hash == ledger_hash(run)
            and (not run.quality_provider or a.executor == run.quality_provider)
            for a in run.quality_audits
        )
    )


def final_audit(
    run: RunResponse, executor: str, mode: str, input_binding: str | None = None
) -> QualityAudit:
    assert run.td_draft and run.prd_draft and run.prd_blueprint
    assert run.prd_approval and run.design_authority and run.td_blueprint
    td = run.td_draft
    structural = True
    try:
        validate_td_obligations(
            td,
            run.prd_draft,
            run.prd_approval,
            run.design_authority,
            run.td_blueprint,
            extract_prd_obligations(run.prd_draft, run.prd_blueprint),
        )
    except ValueError:
        structural = False
    issues, _ = project_quality(td, run.quality_issues, run.td_blueprint)
    passed = (
        structural
        and check_td_readiness(td).ready
        and all(i.status in ("resolved", "accepted") for i in issues)
    )
    passed = passed and all(
        any(
            r.issue_id == i.issue_id
            and r.td_revision == td.revision
            and r.td_content_hash == td.content_hash
            and bool(r.disclosure_text.strip())
            for r in run.quality_risk_acceptances
        )
        for i in run.quality_issues
        if i.status == "accepted"
    )
    if mode == "human":
        passed = passed and bool(run.td_review and run.td_review.status == "ready")
    return QualityAudit(
        audit_id=str(uuid4()),
        td_revision=td.revision,
        td_content_hash=td.content_hash,
        authority_pack_hash=td.authority_pack_hash,
        obligations_hash=digest([i.model_dump(mode="json") for i in td.obligations]),
        ledger_hash=ledger_hash(run),
        executor=executor,
        semantic_mode="human" if mode == "human" else "model",
        passed=passed,
        checks=(
            "structure",
            "blueprint_references",
            "frozen_obligations",
            "issue_ledger",
            "risk_versions",
            "human_semantics" if mode == "human" else "model_semantics",
        ),
        input_binding=input_binding,
    )


def make_task(
    run: RunResponse,
    mode: Literal["discover", "repair", "verify", "final_audit"],
    resources: ModelResources,
    target: QualityIssueRecord | None = None,
) -> ModelTaskInput:
    assert run.prd_draft and run.td_draft and run.td_blueprint and run.design_authority
    data = QualityTaskData(
        mode=mode,
        run_id=run.run_id,
        prd=ReviewDocument(
            document_id="prd",
            revision=run.prd_draft.revision,
            content_hash=run.prd_draft.content_hash,
            content=run.prd_draft.content,
        ),
        td=ReviewDocument(
            document_id="td",
            revision=run.td_draft.revision,
            content_hash=run.td_draft.content_hash,
            content=run.td_draft.content,
        ),
        blueprint=run.td_blueprint,
        authority=run.design_authority,
        obligations=run.td_draft.obligations,
        issues=tuple(i for i in run.quality_issues if i.producer_kind == "model")
        if mode == "verify"
        else ((target,) if target else run.quality_issues),
        target_issue_id=target.issue_id if target else None,
        section_id=next(
            (s for s, title in TD_SECTION_TITLES.items() if target and title == target.section_id),
            None,
        ),
        baseline_content_hash=run.td_draft.content_hash,
        technical_decisions=tuple(
            ModelTechnicalChoice(request_id=i.request_id, answer=i.answer)
            for i in run.technical_decisions
        ),
        risk_acceptances=tuple(i.model_dump_json() for i in run.quality_risk_acceptances),
    )
    # Verify deterministic targets too, without asking the model to close them.
    if mode == "verify" and target and target.producer_kind != "model":
        data = data.model_copy(update={"issues": (*data.issues, target)})
    return build_task("td_quality", data, resources)


def merge_findings(run: RunResponse, output: ModelTaskOutput) -> RunResponse:
    assert run.td_draft
    issues = {i.issue_id: i for i in run.quality_issues}
    for f in output.semantic_findings:
        identity = digest(
            ["model", f.rule_id, f.section_id.value, f.authority_ref, f.reason, f.start, f.end]
        )[:24]
        prior = issues.get(identity)
        dismissed = any(
            d.issue_id == identity
            and d.td_revision == run.td_draft.revision
            and d.td_content_hash == run.td_draft.content_hash
            for d in run.quality_issue_decisions
        )
        issues[identity] = QualityIssueRecord(
            issue_id=identity,
            validator_id="semantic_reviewer",
            rule_id=f.rule_id,
            section_id=TD_SECTION_TITLES[f.section_id],
            authority_ref=f.authority_ref,
            producer_kind="model",
            disposition=f.disposition,
            suggestion=f.suggestion,
            evidence=f.excerpt,
            evidence_start=f.start,
            evidence_end=f.end,
            severity="blocker" if f.disposition != "repair" else f.severity,
            status=(
                "resolved"
                if dismissed
                else "failed"
                if prior and prior.attempts >= 3
                else "reopened"
                if prior and prior.status == "resolved"
                else prior.status
                if prior
                else "open"
            ),
            attempts=prior.attempts if prior else 0,
            last_failure=(
                None
                if dismissed
                else (prior.last_failure or "issue_budget_exhausted")
                if prior and prior.attempts >= 3
                else prior.last_failure
                if prior
                else None
            ),
            first_td_revision=prior.first_td_revision if prior else run.td_draft.revision,
            latest_td_revision=run.td_draft.revision,
        )
    return run.model_copy(update={"quality_issues": tuple(issues.values())})


def execute_cycle(
    run: RunResponse, request: QualityCycleRequest, model: QualityModel, resources: ModelResources
) -> RunResponse:
    """Stage a bounded batch; caller rechecks authority and commits exactly once."""
    assert run.td_draft
    baseline = run
    bindings: list[str] = []
    observations: list[str] = []
    steps = 0
    reason = "step_limit"
    outcome: Literal["continue", "diagnose", "final_audit", "ready"] = "continue"
    final_binding: str | None = None

    def invoke(
        mode: Literal["discover", "repair", "verify", "final_audit"],
        current: RunResponse,
        target: QualityIssueRecord | None = None,
    ) -> ModelTaskOutput:
        task = make_task(current, mode, resources, target)
        bindings.append(task.input_binding)
        output = validate_task_output(task, model.execute(task))
        observations.append(
            json.dumps(
                {
                    "mode": mode,
                    "input_binding": task.input_binding,
                    "td_revision": current.td_draft.revision if current.td_draft else None,
                    "td_hash": current.td_draft.content_hash if current.td_draft else None,
                    "output": output.model_dump(mode="json", exclude={"content"}),
                    "candidate_hash": sha256(output.content.encode()).hexdigest()
                    if output.content
                    else None,
                },
                ensure_ascii=False,
            )
        )
        return output

    try:
        # Omission from a discovery response is never a resolution signal.
        run = merge_findings(run, invoke("discover", run))
        for _ in range(request.max_steps):
            assert run.td_draft
            issues, _gate = project_quality(run.td_draft, run.quality_issues, run.td_blueprint)
            run = run.model_copy(update={"quality_issues": issues})
            active = [i for i in issues if i.status not in ("resolved", "accepted")]
            if any(i.disposition != "repair" for i in active):
                reason, outcome = "human_decision_required", "diagnose"
                break
            if any(i.attempts >= 3 for i in active):
                reason, outcome = "issue_budget_exhausted", "diagnose"
                break
            if not active:
                final = invoke("final_audit", run)
                run = merge_findings(run, final)
                final_binding = final.input_binding
                if any(i.status not in ("resolved", "accepted") for i in run.quality_issues):
                    reason, outcome = "final_audit_findings", "continue"
                else:
                    reason, outcome = "final_audit_complete", "ready"
                break
            target = sorted(active, key=lambda i: (i.severity != "blocker", i.issue_id))[0]
            section = next(
                (s for s, title in TD_SECTION_TITLES.items() if title == target.section_id), None
            )
            if section is None:
                reason, outcome = "scope_not_repairable", "diagnose"
                break
            generated = invoke("repair", run, target)
            assert generated.content is not None
            draft = run.td_draft
            assert draft is not None
            result = apply_quality_patch(
                draft.content,
                target.section_id,
                generated.content,
                expected_hash=draft.content_hash,
                target_check=lambda _: True,
                regression_check=lambda _: True,
            )
            candidate_hash = sha256(result.content.encode()).hexdigest()
            reason = result.reason or "target_still_present"
            successful = False
            candidate = run
            if result.committed:
                revision = TdRevision.model_validate(
                    draft.model_dump()
                    | {
                        "revision": draft.revision + 1,
                        "content": result.content,
                        "content_hash": candidate_hash,
                        "changed_section_id": section,
                        "feedback": f"质量 Issue {target.issue_id}",
                        "actor_claim": request.actor_claim,
                        "command_id": request.command_id,
                    }
                )
                candidate = run.model_copy(update={"td_draft": revision})
                assert run.prd_draft and run.prd_approval and run.design_authority
                assert run.td_blueprint and run.prd_blueprint
                validate_td_obligations(
                    revision,
                    run.prd_draft,
                    run.prd_approval,
                    run.design_authority,
                    run.td_blueprint,
                    extract_prd_obligations(run.prd_draft, run.prd_blueprint),
                )
                found, _ = project_quality(revision, run.quality_issues, run.td_blueprint)
                previous_ids = {
                    i.issue_id
                    for i in run.quality_issues
                    if i.status not in ("resolved", "accepted")
                }
                regressions = [
                    i
                    for i in found
                    if i.producer_kind == "deterministic"
                    and i.status not in ("resolved", "accepted")
                    and i.issue_id not in previous_ids
                ]
                if regressions:
                    reason = "regression_detected"
                elif (
                    any(
                        generated.content.strip()
                        == old.content.split("## " + target.section_id + "\n", 1)[1]
                        .split("\n## ", 1)[0]
                        .strip()
                        for old in run.td_revisions
                        if "## " + target.section_id + "\n" in old.content
                    )
                    or candidate_hash == draft.content_hash
                    or any(a.candidate_hash == candidate_hash for a in run.quality_patch_attempts)
                ):
                    reason = "repeated_candidate"
                else:
                    verification = invoke("verify", candidate, target)
                    verdicts = {
                        v.issue_id: v.no_longer_observed for v in verification.verifications
                    }
                    still_target = any(
                        i.issue_id == target.issue_id and i.status != "resolved"
                        for i in found
                        if i.producer_kind == "deterministic"
                    )
                    protected = [
                        i for i in issues if i.producer_kind == "model" and i.status == "resolved"
                    ]
                    if still_target or not verdicts.get(target.issue_id, False):
                        reason = "target_still_present"
                    elif verification.semantic_findings or any(
                        not verdicts.get(i.issue_id, False) for i in protected
                    ):
                        reason = "semantic_regression"
                    else:
                        successful = True
                        candidate = candidate.model_copy(
                            update={
                                "quality_issues": tuple(
                                    i.model_copy(
                                        update={
                                            "status": "resolved",
                                            "last_failure": None,
                                            "latest_td_revision": revision.revision,
                                        }
                                    )
                                    if verdicts.get(i.issue_id) and i.producer_kind == "model"
                                    else i
                                    for i in found
                                )
                            }
                        )
            steps += 1
            attempt = QualityPatchAttempt(
                issue_id=target.issue_id,
                command_id=request.command_id,
                baseline_revision=draft.revision,
                baseline_hash=draft.content_hash,
                candidate_hash=candidate_hash,
                input_bindings=tuple(bindings),
                outcome="committed" if successful else "rejected",
                reason=None if successful else reason,
            )
            issue_source = candidate.quality_issues if successful else run.quality_issues
            changed_issues = tuple(
                i.model_copy(
                    update={
                        "attempts": i.attempts + 1,
                        "status": "resolved"
                        if successful
                        else "failed"
                        if i.attempts + 1 >= 3
                        else "reopened",
                        "last_failure": None if successful else reason,
                    }
                )
                if i.issue_id == target.issue_id
                else i
                for i in issue_source
            )
            if successful:
                assert candidate.td_draft and run.td_review
                stale = run.td_review.model_copy(
                    update={
                        "binding": current_td_review_binding(candidate),
                        "status": "stale",
                        "review_revision": run.td_review.review_revision + 1,
                    }
                )
                run = candidate.model_copy(
                    update={
                        "td_revisions": (*run.td_revisions, candidate.td_draft),
                        "td_review": stale,
                    }
                )
            run = run.model_copy(
                update={
                    "quality_issues": changed_issues,
                    "quality_patch_attempts": (*run.quality_patch_attempts, attempt),
                }
            )
            if not successful and reason in (
                "repeated_candidate",
                "regression_detected",
                "semantic_regression",
            ):
                outcome = "diagnose"
                break
        else:
            if any(i.attempts >= 3 and i.status != "resolved" for i in run.quality_issues):
                reason, outcome = "issue_budget_exhausted", "diagnose"
    except (QualityProviderError, ModelBoundaryError) as error:
        reason, outcome = error.code, "diagnose"
    except ValueError:
        reason, outcome = "quality_candidate_invalid", "diagnose"
    assert run.td_draft
    execution = QualityExecution(
        command_id=request.command_id,
        provider_id=model.identity,
        td_revision=run.td_draft.revision,
        td_content_hash=run.td_draft.content_hash,
        input_bindings=tuple(bindings),
        observations=tuple(observations),
        steps=steps,
        outcome=outcome,
        reason=reason,
    )
    run = run.model_copy(update={"quality_executions": (*run.quality_executions, execution)})
    if outcome == "ready" and final_binding:
        audit = final_audit(run, model.identity, "model", final_binding)
        run = run.model_copy(update={"quality_audits": (*run.quality_audits, audit)})
    # All changes remain staged until the Runner verifies the baseline and commits.
    assert baseline.prd_draft == run.prd_draft and baseline.design_authority == run.design_authority
    return run

"""Semantic quality candidates cannot replace versioned domain authority."""

import json

import pytest
from deliveryflow_contracts.model_tasks import QualityTaskData
from deliveryflow_contracts.quality import QualityCycleRequest
from deliveryflow_contracts.runs import AvailableCommand
from deliveryflow_speccraft.model_boundary import (
    ModelBoundaryError,
    validate_task_output,
)
from deliveryflow_speccraft.quality_engine import QualityProviderError, make_task
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import DuplicateCommand, GovernanceError, RunRunner
from governance_helpers import td_review_request
from test_td_quality import ROOT
from test_td_review import approval
from test_td_runner import approve_prd, prd_ready


class ScriptedModel:
    identity = "scripted-quality-v1"

    def __init__(self, *, defect=True, bad_patch=False, failure=None):
        self.defect = defect
        self.bad_patch = bad_patch
        self.failure = failure
        self.calls = []

    def execute(self, task):
        self.calls.append(task)
        if self.failure:
            raise self.failure
        p = task.payload
        assert isinstance(p, QualityTaskData)
        base = {
            "task_kind": "td_quality",
            "input_binding": task.input_binding,
            "cited_ids": p.blueprint.authority_ids + p.blueprint.obligation_ids,
        }
        # frontend is unbound in the sample; no reference text needs replacement.
        title = "## 前端页面、组件、交互与状态管理\n"
        start = p.td.content.index(title) + len(title)
        end = p.td.content.find("\n## ", start)
        end = len(p.td.content) if end < 0 else end
        body = p.td.content[start:end].strip()
        if p.mode in ("discover", "final_audit"):
            if self.defect and "明确处理失败" not in body:
                base["semantic_findings"] = [
                    {
                        "rule_id": "failure_missing",
                        "section_id": "frontend",
                        "authority_ref": p.blueprint.authority_ids[0],
                        "start": start,
                        "end": start + len(body),
                        "excerpt": body,
                        "reason": "界面未交代失败",
                        "suggestion": "明确处理失败",
                        "severity": "blocker",
                        "disposition": "repair",
                    }
                ]
        elif p.mode == "repair":
            base["content"] = body if self.bad_patch else body + "\n明确处理失败。"
        elif p.mode == "verify":
            base["verifications"] = [
                {
                    "issue_id": i.issue_id,
                    "no_longer_observed": "明确处理失败" in body,
                    "rationale": "逐项核对当前版本",
                }
                for i in p.issues
            ]
        return base


def subject(model, database=None):
    return RunRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
        database_path=database,
        quality_model=model,
    )


def awaiting(s):
    return approve_prd(s, prd_ready(s))


def request(run, command="cycle-1", steps=3):
    return QualityCycleRequest(
        governance_contract_version=2,
        command_id=command,
        actor_claim="tester",
        expected_td_revision=run.td_draft.revision,
        expected_td_content_hash=run.td_draft.content_hash,
        expected_review_revision=run.td_review.review_revision,
        max_steps=steps,
    )


def test_cycle_repairs_audits_and_requires_new_human_review():
    model = ScriptedModel()
    s = subject(model)
    original = awaiting(s)
    reviewed = s.record_td_review(original.run_id, td_review_request(original))
    assert AvailableCommand.APPROVE_TD not in reviewed.available_commands
    fixed = s.run_td_quality(original.run_id, request(reviewed))
    assert fixed.td_draft.revision == 2
    assert fixed.prd_draft == original.prd_draft
    assert fixed.design_authority == original.design_authority
    assert fixed.quality_issues[0].status == "resolved"
    assert fixed.quality_issues[0].attempts == 1
    assert fixed.quality_audit_current
    assert fixed.td_review.status == "stale"
    assert fixed.quality_executions[-1].outcome == "ready"
    assert len(fixed.quality_executions[-1].observations) == 4
    assert AvailableCommand.APPROVE_TD not in fixed.available_commands
    human = s.record_td_review(fixed.run_id, td_review_request(fixed, "review-fixed"))
    done = s.approve_td(fixed.run_id, approval(human))
    assert done.delivery_spec.td.content_hash == fixed.td_draft.content_hash


def test_model_failure_is_diagnosis_not_zero_findings_and_survives_restart(tmp_path):
    m = ScriptedModel(failure=QualityProviderError("quality_provider_network_error"))
    s = subject(m, tmp_path / "runs.db")
    run = awaiting(s)
    failed = s.run_td_quality(run.run_id, request(run))
    assert failed.quality_executions[-1].reason == "quality_provider_network_error"
    assert not failed.quality_audit_current
    assert not failed.quality_audits
    assert not failed.quality_patch_attempts
    restored = subject(m, tmp_path / "runs.db").get_run(run.run_id)
    assert restored == failed
    with pytest.raises(DuplicateCommand):
        s.run_td_quality(run.run_id, request(failed))


def test_invalid_request_does_not_call_model_or_consume_command():
    m = ScriptedModel()
    s = subject(m)
    run = awaiting(s)
    from deliveryflow_speccraft.runner import ContentHashConflict

    with pytest.raises(ContentHashConflict):
        s.run_td_quality(
            run.run_id,
            request(run).model_copy(update={"expected_td_content_hash": "0" * 64}),
        )
    assert not m.calls and s.get_run(run.run_id) == run
    assert "cycle-1" not in s._used_command_ids[run.run_id]


def test_repeated_candidate_stops_without_publishing_new_td():
    s = subject(ScriptedModel(bad_patch=True))
    run = awaiting(s)
    stopped = s.run_td_quality(run.run_id, request(run, steps=8))
    assert stopped.td_draft == run.td_draft
    assert stopped.quality_executions[-1].reason == "repeated_candidate"
    assert stopped.quality_executions[-1].steps == 1
    assert stopped.quality_issues[0].attempts == 1
    assert not stopped.quality_audit_current


def test_discovery_omission_does_not_close_semantic_issue():
    m = ScriptedModel(bad_patch=True)
    s = subject(m)
    run = awaiting(s)
    stopped = s.run_td_quality(run.run_id, request(run))
    m.defect = False
    again = s.run_td_quality(run.run_id, request(stopped, "cycle-2"))
    assert again.quality_issues[0].status != "resolved"
    assert again.quality_issues[0].attempts == 2
    last = s.run_td_quality(run.run_id, request(again, "cycle-3"))
    assert last.quality_issues[0].attempts == 3
    end = s.run_td_quality(run.run_id, request(last, "cycle-4"))
    assert end.quality_executions[-1].reason == "issue_budget_exhausted"
    assert len(end.quality_patch_attempts) == 3


def test_evidence_purpose_limits_and_unknown_references_rejected():
    m = ScriptedModel()
    s = subject(m)
    run = awaiting(s)
    from deliveryflow_contracts.model_tasks import ModelResources

    task = make_task(
        run, "discover", ModelResources(template="", guide="", self_check="")
    )
    valid = m.execute(task)
    for field, value in [
        ("authority_ref", "forged"),
        ("start", 0),
        ("excerpt", "forged"),
    ]:
        bad = json.loads(json.dumps(valid))
        bad["semantic_findings"][0][field] = value
        with pytest.raises(ModelBoundaryError):
            validate_task_output(task, bad)
    with pytest.raises(ModelBoundaryError):
        validate_task_output(
            task, {**valid, "semantic_findings": valid["semantic_findings"] * 33}
        )
    with pytest.raises(ModelBoundaryError):
        validate_task_output(task, {**valid, "content": "forbidden write"})
    with pytest.raises(ModelBoundaryError):
        validate_task_output(task, {**valid, "input_binding": "0" * 64})
    with pytest.raises(ModelBoundaryError):
        validate_task_output(task, b"x" * (256 * 1024 + 1))


def test_model_output_error_preserves_issue_and_records_no_pass():
    m = ScriptedModel(failure=ModelBoundaryError("model_output_invalid"))
    s = subject(m)
    run = awaiting(s)
    failed = s.run_td_quality(run.run_id, request(run))
    assert failed.quality_executions[-1].reason == "model_output_invalid"
    assert not failed.quality_audit_current


def test_commit_failure_rolls_back_entire_batch(monkeypatch):
    import sqlite3

    m = ScriptedModel()
    s = subject(m)
    run = awaiting(s)
    original = s._used_command_ids[run.run_id].__class__.add

    def fail(self, command):
        raise sqlite3.OperationalError("simulated store failure")

    monkeypatch.setattr(s._used_command_ids[run.run_id].__class__, "add", fail)
    with pytest.raises(sqlite3.OperationalError):
        s.run_td_quality(run.run_id, request(run))
    monkeypatch.setattr(s._used_command_ids[run.run_id].__class__, "add", original)
    assert s.get_run(run.run_id) == run
    assert "cycle-1" not in s._used_command_ids[run.run_id]


def test_stale_final_audit_cannot_enable_approval():
    s = subject(ScriptedModel(defect=False))
    run = awaiting(s)
    audited = s.run_td_quality(run.run_id, request(run))
    reviewed = s.record_td_review(run.run_id, td_review_request(audited))
    assert AvailableCommand.APPROVE_TD in reviewed.available_commands
    tampered = s._validated_update(reviewed, {"quality_audits": ()})
    with s._lock:
        s._runs[run.run_id] = tampered
    with pytest.raises(GovernanceError, match="td_final_audit_required"):
        s.approve_td(run.run_id, approval(tampered))


def test_human_false_positive_decision_is_versioned_and_does_not_override_guard():
    from deliveryflow_contracts.quality import QualityIssueDecisionRequest

    m = ScriptedModel(bad_patch=True)
    s = subject(m)
    run = awaiting(s)
    stopped = s.run_td_quality(run.run_id, request(run))
    stopped = s.run_td_quality(run.run_id, request(stopped, "budget-2"))
    stopped = s.run_td_quality(run.run_id, request(stopped, "budget-3"))
    assert stopped.quality_issues[0].attempts == 3
    decision = QualityIssueDecisionRequest(
        **request(stopped, "dismiss").model_dump(),
        issue_id=stopped.quality_issues[0].issue_id,
        rationale="人工核对后确认误报",
        user_confirmed=True,
    )
    dismissed = s.decide_td_issue(run.run_id, decision)
    assert dismissed.quality_issues[0].status == "resolved"
    assert (
        dismissed.quality_issue_decisions[-1].td_content_hash
        == run.td_draft.content_hash
    )
    audited = s.run_td_quality(run.run_id, request(dismissed, "audit"))
    assert audited.quality_audit_current
    assert audited.quality_issues[0].status == "resolved"


def test_api_quality_command_keeps_committed_sync_failure_boundary(monkeypatch):
    from deliveryflow_speccraft.workflow import RunWorkflow
    from fastapi.testclient import TestClient

    from apps.api import main

    s = subject(ScriptedModel(defect=False))
    run = awaiting(s)
    workflow = RunWorkflow(s)
    monkeypatch.setattr(main, "workflow", workflow)
    original = workflow._ensure_synced
    calls = 0

    def fail_after_commit(current, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated graph failure")
        return original(current, **kwargs)

    monkeypatch.setattr(workflow, "_ensure_synced", fail_after_commit)
    client = TestClient(main.app)
    result = client.post(
        f"/api/runs/{run.run_id}/td/quality/run", json=request(run).model_dump()
    )
    assert result.status_code == 503 and result.json()["detail"]["committed"] is True
    monkeypatch.setattr(workflow, "_ensure_synced", original)
    reread = client.get(f"/api/runs/{run.run_id}")
    assert reread.status_code == 200 and reread.json()["quality_audit_current"]


def test_model_call_race_rejects_staged_batch_without_overwriting_human_review():
    m = ScriptedModel(defect=False)
    s = subject(m)
    run = awaiting(s)
    original = m.execute
    changed = False

    def racing(task):
        nonlocal changed
        if not changed:
            changed = True
            s.record_td_review(run.run_id, td_review_request(run))
        return original(task)

    m.execute = racing
    with pytest.raises(GovernanceError, match="td_review_conflict"):
        s.run_td_quality(run.run_id, request(run))
    current = s.get_run(run.run_id)
    assert current.td_review.status == "ready"
    assert not current.quality_executions
    assert "cycle-1" not in s._used_command_ids[run.run_id]


def test_model_context_limit_rejects_before_invocation():
    from deliveryflow_contracts.model_tasks import ModelResources

    s = subject(ScriptedModel())
    run = awaiting(s)
    with pytest.raises(ModelBoundaryError, match="model task rejected") as failure:
        make_task(
            run,
            "discover",
            ModelResources(template="x" * (128 * 1024), guide="", self_check=""),
        )
    assert failure.value.code == "model_context_too_large"


def test_final_audit_can_discover_new_issue_and_block_approval():
    class FinalFinding(ScriptedModel):
        def execute(self, task):
            if task.payload.mode == "final_audit":
                self.defect = True
            else:
                self.defect = False
            return super().execute(task)

    s = subject(FinalFinding())
    run = awaiting(s)
    result = s.run_td_quality(run.run_id, request(run))
    assert result.quality_executions[-1].reason == "final_audit_findings"
    assert result.quality_issues and not result.quality_audit_current
    assert result.td_draft == run.td_draft


def test_semantic_regression_rejects_candidate_and_preserves_td():
    class Regression(ScriptedModel):
        def execute(self, task):
            if task.payload.mode == "verify":
                bad = super().execute(task)
                # Return a new exact-evidence finding on the candidate alongside the target verdict.
                self.defect = True
                p = task.payload
                start = p.td.content.index("明确处理失败")
                bad["semantic_findings"] = [
                    {
                        "rule_id": "new_regression",
                        "section_id": "frontend",
                        "authority_ref": p.blueprint.authority_ids[0],
                        "start": start,
                        "end": start + len("明确处理失败"),
                        "excerpt": "明确处理失败",
                        "reason": "新缺陷",
                        "suggestion": "重新设计",
                        "severity": "blocker",
                        "disposition": "repair",
                    }
                ]
                return bad
            return super().execute(task)

    s = subject(Regression())
    run = awaiting(s)
    result = s.run_td_quality(run.run_id, request(run))
    assert result.quality_executions[-1].reason == "semantic_regression"
    assert result.td_draft == run.td_draft
    assert result.quality_issues[0].attempts == 1


def test_total_step_bound_and_rejected_candidate_receipt_survive_restart(tmp_path):
    class Unfixed(ScriptedModel):
        def execute(self, task):
            response = super().execute(task)
            if task.payload.mode == "verify":
                response["verifications"] = [
                    dict(v, no_longer_observed=False) for v in response["verifications"]
                ]
            return response

    m = Unfixed()
    s = subject(m, tmp_path / "run.db")
    run = awaiting(s)
    limited = s.run_td_quality(run.run_id, request(run, steps=1))
    assert limited.quality_executions[-1].steps == 1
    assert limited.quality_executions[-1].reason == "target_still_present"
    assert limited.td_draft == run.td_draft
    restarted = subject(m, tmp_path / "run.db")
    assert restarted.get_run(run.run_id).quality_issues[0].attempts == 1
    with pytest.raises(DuplicateCommand):
        restarted.run_td_quality(run.run_id, request(limited))

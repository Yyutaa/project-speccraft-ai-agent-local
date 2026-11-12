"""Quality execution consumes a persisted total budget before provider calls."""

import importlib

import pytest
from deliveryflow_speccraft.runner import ContentHashConflict
from test_composition import ROOT
from test_quality_cycle import ScriptedModel, awaiting, request


def bounded(model, path, *, calls=2, candidates=8):
    from deliveryflow_speccraft.composition import build_runner

    contracts = importlib.import_module("deliveryflow_contracts.execution")
    return build_runner(
        ROOT,
        database_path=path,
        quality_model=model,
        model_budget_policy=contracts.ModelBudgetPolicy(
            max_model_calls=calls,
            max_candidates=candidates,
        ),
    )


def test_new_command_and_restart_do_not_restore_model_call_budget(tmp_path):
    model = ScriptedModel(defect=False)
    runner = bounded(model, tmp_path / "runs.db")
    run = awaiting(runner)
    audited = runner.run_td_quality(run.run_id, request(run))
    assert audited.quality_audit_current
    assert len(model.calls) == 2
    # A new server default applies only to future Runs, never this frozen policy.
    restarted = bounded(model, tmp_path / "runs.db", calls=100)
    stopped = restarted.run_td_quality(run.run_id, request(audited, "another-command"))
    assert len(model.calls) == 2
    assert stopped.quality_executions[-1].reason == "run_model_budget_exhausted"
    assert not stopped.quality_audit_current
    assert stopped.td_draft == audited.td_draft
    assert restarted.get_model_budget(run.run_id).model_calls == 2
    assert restarted.get_model_budget(run.run_id).policy.max_model_calls == 2


def test_provider_failure_consumes_call_but_not_candidate(tmp_path):
    from deliveryflow_speccraft.quality_engine import QualityProviderError

    model = ScriptedModel(
        failure=QualityProviderError("quality_provider_network_error")
    )
    runner = bounded(model, tmp_path / "runs.db", calls=1)
    run = awaiting(runner)
    failed = runner.run_td_quality(run.run_id, request(run))
    assert failed.quality_executions[-1].reason == "quality_provider_network_error"
    usage = runner.get_model_budget(run.run_id)
    assert usage.model_calls == 1 and usage.candidates == 0
    assert runner._runs.model_calls(run.run_id)[0].status == "failed"
    again = runner.run_td_quality(run.run_id, request(failed, "again"))
    assert again.quality_executions[-1].reason == "run_model_budget_exhausted"
    assert len(model.calls) == 1


def test_invalid_request_never_reserves_or_calls_model(tmp_path):
    model = ScriptedModel()
    runner = bounded(model, tmp_path / "runs.db")
    run = awaiting(runner)
    events = runner._runs.events_after(run.run_id, 0)
    with pytest.raises(ContentHashConflict):
        runner.run_td_quality(
            run.run_id,
            request(run).model_copy(
                update={
                    "expected_td_content_hash": "0" * 64,
                }
            ),
        )
    assert runner.get_model_budget(run.run_id).model_calls == 0
    assert runner._runs.events_after(run.run_id, 0) == events
    assert not model.calls


def test_repeat_candidate_charges_once_and_total_limit_prevents_another_repair(
    tmp_path,
):
    model = ScriptedModel(bad_patch=True)
    runner = bounded(model, tmp_path / "runs.db", calls=10, candidates=1)
    run = awaiting(runner)
    failed = runner.run_td_quality(run.run_id, request(run))
    assert runner.get_model_budget(run.run_id).candidates == 1
    stopped = runner.run_td_quality(run.run_id, request(failed, "another-command"))
    assert stopped.quality_executions[-1].reason == "run_candidate_budget_exhausted"
    assert sum(t.payload.mode == "repair" for t in model.calls) == 1
    assert stopped.td_draft == run.td_draft
    assert stopped.quality_issues[0].attempts == 1


def test_final_commit_failure_preserves_domain_but_keeps_real_call_consumption(
    tmp_path, monkeypatch
):
    model = ScriptedModel(defect=False)
    runner = bounded(model, tmp_path / "runs.db")
    run = awaiting(runner)
    command_class = type(runner._used_command_ids[run.run_id])

    def fail(*args):
        raise RuntimeError("simulated commit boundary failure")

    monkeypatch.setattr(command_class, "add", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        runner.run_td_quality(run.run_id, request(run))
    assert runner.get_run(run.run_id) == run
    assert runner.get_model_budget(run.run_id).model_calls == 2
    assert request(run).command_id not in runner._used_command_ids[run.run_id]


def test_manual_issue_patches_share_the_persistent_candidate_budget(tmp_path):
    from deliveryflow_contracts.execution import ModelBudgetPolicy
    from deliveryflow_speccraft.composition import build_runner
    from deliveryflow_speccraft.runner import GovernanceError
    from test_td_quality import patch_request, quality_run

    runner = build_runner(
        ROOT,
        database_path=tmp_path / "runs.db",
        model_budget_policy=ModelBudgetPolicy(max_candidates=1),
    )
    run = quality_run(runner)
    failed = runner.patch_td_issue(run.run_id, patch_request(run, body="still TODO"))
    assert runner.get_model_budget(run.run_id).candidates == 1
    with pytest.raises(GovernanceError, match="run_candidate_budget_exhausted"):
        runner.patch_td_issue(
            run.run_id,
            patch_request(
                failed,
                body="fixed",
                command_id="new-command",
            ),
        )
    assert runner.get_run(run.run_id) == failed
    assert "new-command" not in runner._used_command_ids[run.run_id]


def test_candidate_is_counted_when_provider_fails_during_verification(tmp_path):
    from deliveryflow_speccraft.quality_engine import QualityProviderError

    class VerifyFails(ScriptedModel):
        def execute(self, task):
            if task.payload.mode == "verify":
                self.calls.append(task)
                raise QualityProviderError("quality_provider_network_error")
            result = super().execute(task)
            if task.payload.mode == "repair":
                # Distinct candidates reach verification rather than the repeat guard.
                result["content"] += f"\n本轮候选编号：{len(self.calls)}。"
            return result

    model = VerifyFails()
    runner = bounded(model, tmp_path / "runs.db", calls=20)
    run = awaiting(runner)
    baseline = run.td_draft
    for attempt in range(3):
        run = runner.run_td_quality(run.run_id, request(run, f"try-{attempt}"))
        assert run.td_draft == baseline
        assert run.quality_issues[0].attempts == attempt + 1
        assert run.quality_patch_attempts[-1].outcome == "rejected"
        assert run.quality_patch_attempts[-1].reason == "quality_provider_network_error"
    assert runner.get_model_budget(run.run_id).candidates == 3
    assert run.quality_issues[0].status == "failed"

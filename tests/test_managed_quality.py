"""Background semantic quality reuses the existing repair transaction and human Gate."""

import json
import sqlite3

import httpx
import pytest
from deliveryflow_contracts import execution as contracts
from deliveryflow_contracts.model_tasks import ModelTaskInput
from deliveryflow_speccraft import managed_quality
from deliveryflow_speccraft.providers import DeepSeekProvider
from deliveryflow_speccraft.runner import GovernanceError
from test_provider_adapter import config
from test_quality_cycle import ScriptedModel, awaiting, request, subject


def ready_quality(tmp_path):
    runner = subject(ScriptedModel(), tmp_path / "runs.sqlite3")
    run = awaiting(runner)
    binding = config().binding
    runner._runs.bind_provider(run.run_id, binding)
    run = runner._validated_update(
        run, {"quality_provider": f"{binding.provider}:{binding.model}"}
    )
    runner._runs[run.run_id] = run
    return runner, run


def command(runner, run, identifier="managed-quality", steps=3):
    return contracts.ManagedQualityRequest(
        execution_contract_version=1,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        rationale="检查并修复当前TD",
        user_confirmed=True,
        request=request(run, identifier, steps),
    )


def provider(model=None, handler=None):
    model = model or ScriptedModel()

    def respond(req):
        task = ModelTaskInput.model_validate_json(
            json.loads(req.content)["messages"][1]["content"]
        )
        output = model.execute(task)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output, ensure_ascii=False),
                        },
                    }
                ]
            },
        )

    return DeepSeekProvider(
        config(), client=httpx.Client(transport=httpx.MockTransport(handler or respond))
    )


def test_quality_repairs_audits_but_cannot_approve_and_meters_each_subtask(tmp_path):
    runner, run = ready_quality(tmp_path)
    cmd = command(runner, run)
    acceptance = managed_quality.submit_quality(runner, run.run_id, cmd)
    assert (
        runner.get_run(run.run_id) == run
    )  # API does no model or optimistic mutation.
    assert runner.get_model_budget(run.run_id).model_calls == 0
    done = managed_quality.execute_quality_job(
        runner, provider(), runner._runs.claim_next("worker")
    )
    assert done.status == "succeeded"
    fixed = runner.get_run(run.run_id)
    assert fixed.td_draft.revision == 2 and fixed.quality_audit_current
    assert fixed.quality_issues[0].status == "resolved"
    assert fixed.quality_issues[0].attempts == 1
    assert fixed.td_approval is None and fixed.delivery_spec is None
    assert fixed.td_review.status == "stale"
    assert fixed.prd_draft == run.prd_draft and fixed.prd_approval == run.prd_approval
    assert runner.get_model_budget(run.run_id).model_calls == 4
    assert runner.get_model_budget(run.run_id).candidates == 1
    calls = runner._runs.model_calls(run.run_id)
    assert len({c.input_binding for c in calls}) == 4
    assert runner.get_command(run.run_id, acceptance.command_id).domain_committed


def test_quality_provider_failure_records_diagnosis_never_empty_pass(tmp_path):
    runner, run = ready_quality(tmp_path)
    accepted = managed_quality.submit_quality(runner, run.run_id, command(runner, run))
    done = managed_quality.execute_quality_job(
        runner,
        provider(handler=lambda _: httpx.Response(401)),
        runner._runs.claim_next("worker"),
    )
    assert (
        done.status == "succeeded"
    )  # The durable diagnostic batch committed, not quality passed.
    current = runner.get_run(run.run_id)
    assert current.quality_executions[-1].reason == "provider_auth_failed"
    assert current.quality_executions[-1].outcome == "diagnose"
    assert not current.quality_audit_current and current.td_draft == run.td_draft
    assert runner.get_command(run.run_id, accepted.command_id).domain_committed
    assert runner.get_model_budget(run.run_id).model_calls == 1


def test_budget_exhaustion_is_diagnosis_not_network_or_approval(tmp_path):
    runner, run = ready_quality(tmp_path)
    store = runner._runs
    store._connection.execute(
        "UPDATE model_budgets SET calls=31 WHERE run_id=?", (run.run_id,)
    )
    managed_quality.submit_quality(runner, run.run_id, command(runner, run))
    done = managed_quality.execute_quality_job(
        runner, provider(), store.claim_next("worker")
    )
    assert done.status == "succeeded"
    current = runner.get_run(run.run_id)
    assert current.quality_executions[-1].reason == "run_model_budget_exhausted"
    assert not current.quality_audit_current and current.td_draft == run.td_draft
    assert runner.get_model_budget(run.run_id).model_calls == 32


def test_cancel_during_quality_discards_staged_result_and_consumption_survives(
    tmp_path,
):
    runner, run = ready_quality(tmp_path)
    accepted = managed_quality.submit_quality(runner, run.run_id, command(runner, run))

    def cancel(_):
        runner._runs.cancel_job(accepted.job_id)
        return httpx.Response(401)

    done = managed_quality.execute_quality_job(
        runner, provider(handler=cancel), runner._runs.claim_next("worker")
    )
    assert done.status == "cancelled"
    assert runner.get_run(run.run_id) == run
    assert runner.get_model_budget(run.run_id).model_calls == 1
    assert runner._runs.model_calls(run.run_id)[0].status == "interrupted"


def test_final_commit_failure_is_atomic_and_recovery_keeps_cost(tmp_path):
    runner, run = ready_quality(tmp_path)
    accepted = managed_quality.submit_quality(runner, run.run_id, command(runner, run))
    store = runner._runs
    store._connection.execute(
        "CREATE TRIGGER fail_finish BEFORE INSERT ON run_events WHEN NEW.event_type='job.finished' BEGIN SELECT RAISE(ABORT,'commit failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="commit failed"):
        managed_quality.execute_quality_job(
            runner, provider(), store.claim_next("worker")
        )
    assert runner.get_run(run.run_id) == run
    assert runner.get_model_budget(run.run_id).model_calls == 4
    assert runner.get_model_budget(run.run_id).candidates == 1
    assert store.get_command(run.run_id, accepted.command_id).status == "accepted"
    store._connection.execute("DROP TRIGGER fail_finish")
    store._connection.execute(
        "UPDATE model_jobs SET lease_until=0 WHERE job_id=?", (accepted.job_id,)
    )
    done = managed_quality.execute_quality_job(
        runner, provider(), store.claim_next("new-worker")
    )
    assert (
        done.status == "succeeded" and runner.get_run(run.run_id).quality_audit_current
    )
    assert runner.get_model_budget(run.run_id).model_calls == 8


@pytest.mark.parametrize(
    "change,code",
    [
        ({"expected_run_version": 0}, "run_version_conflict"),
        ({"request_hash": True}, "content_hash_conflict"),
    ],
)
def test_stale_quality_requests_leave_no_receipt_or_cost(tmp_path, change, code):
    runner, run = ready_quality(tmp_path)
    cmd = command(runner, run)
    if change.get("request_hash"):
        cmd = cmd.model_copy(
            update={
                "request": cmd.request.model_copy(
                    update={"expected_td_content_hash": "0" * 64}
                )
            }
        )
    else:
        cmd = cmd.model_copy(update=change)
    before = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError) as error:
        managed_quality.submit_quality(runner, run.run_id, cmd)
    assert error.value.code == code
    assert runner.get_snapshot(run.run_id) == before
    with pytest.raises(KeyError):
        runner.get_command(run.run_id, cmd.request.command_id)


def test_uncommitted_candidates_do_not_reset_issue_limit_after_restart(tmp_path):
    runner, run = ready_quality(tmp_path)
    store = runner._runs
    # Discover the stable identity, but leave all three candidates outside Run state.
    from deliveryflow_speccraft.model_boundary import validate_task_output
    from deliveryflow_speccraft.quality_engine import make_task, merge_findings

    task = make_task(run, "discover", managed_quality.resources(runner))
    found = merge_findings(
        run, validate_task_output(task, ScriptedModel().execute(task))
    )
    issue = found.quality_issues[0]
    for i in range(3):
        store.reserve_candidate(
            run.run_id, f"interrupted-{i}", issue.issue_id, str(i) * 64
        )
    accepted = managed_quality.submit_quality(runner, run.run_id, command(runner, run))
    store.close()
    restored = subject(ScriptedModel(), tmp_path / "runs.sqlite3")
    result = managed_quality.execute_quality_job(
        restored, provider(), restored._runs.claim_next("new")
    )
    assert result.status == "succeeded"
    current = restored.get_run(run.run_id)
    assert current.quality_executions[-1].reason == "issue_budget_exhausted"
    assert current.td_draft == run.td_draft
    assert restored.get_model_budget(run.run_id).model_calls == 1  # Discovery only.
    assert restored.get_model_budget(run.run_id).candidates == 3
    assert restored.get_command(run.run_id, accepted.command_id).domain_committed


def test_repeated_candidate_stops_and_budget_and_current_body_are_retained(tmp_path):
    runner, run = ready_quality(tmp_path)
    managed_quality.submit_quality(runner, run.run_id, command(runner, run, steps=8))
    result = managed_quality.execute_quality_job(
        runner,
        provider(ScriptedModel(bad_patch=True)),
        runner._runs.claim_next("worker"),
    )
    current = runner.get_run(run.run_id)
    assert result.status == "succeeded"
    assert current.quality_executions[-1].reason == "repeated_candidate"
    assert current.quality_issues[0].attempts == 1
    assert current.td_draft == run.td_draft and not current.quality_audit_current
    assert runner.get_model_budget(run.run_id).model_calls == 2


def test_quality_duplicate_or_changed_payload_never_enqueues_again(tmp_path):
    runner, run = ready_quality(tmp_path)
    cmd = command(runner, run)
    managed_quality.submit_quality(runner, run.run_id, cmd)
    with pytest.raises(GovernanceError, match="duplicate_command"):
        managed_quality.submit_quality(runner, run.run_id, cmd)
    with pytest.raises(GovernanceError, match="command_payload_conflict"):
        managed_quality.submit_quality(
            runner, run.run_id, cmd.model_copy(update={"rationale": "changed"})
        )
    assert len(runner._runs.jobs_for_run(run.run_id)) == 1


def test_quality_rest_returns_202_and_dispatcher_executes_the_durable_job(
    tmp_path, monkeypatch
):
    from deliveryflow_speccraft import managed
    from test_managed_prd_api import client_for

    runner, run = ready_quality(tmp_path)
    client = client_for(runner, monkeypatch)
    response = client.post(
        f"/api/managed/runs/{run.run_id}/td/quality/run",
        json=command(runner, run).model_dump(mode="json"),
    )
    assert response.status_code == 202
    job = response.json()["job_id"]
    summary = client.get(f"/api/runs/{run.run_id}/jobs/{job}").json()
    assert summary["available_commands"] == ["cancel_execution"]
    assert (
        managed.execute_model_job(runner, provider(), owner="api-worker").status
        == "succeeded"
    )
    assert client.get(f"/api/runs/{run.run_id}/snapshot").json()["run"][
        "quality_audit_current"
    ]


def test_cancelled_quality_job_retries_with_new_command_and_preserves_original_limits(
    tmp_path,
):
    from deliveryflow_speccraft import managed
    from test_managed_prd_controls import control

    runner, run = ready_quality(tmp_path)
    service = managed.ManagedRunService(runner)
    accepted = managed_quality.submit_quality(
        runner, run.run_id, command(runner, run, steps=1)
    )
    service.cancel_job(
        run.run_id, accepted.job_id, control(runner, run.run_id, "cancel-quality")
    )
    retried = service.retry_job(
        run.run_id, accepted.job_id, control(runner, run.run_id, "retry-quality")
    )
    job = runner._runs.get_job(retried.job_id)
    assert job.quality_request.command_id == "retry-quality"
    assert job.quality_request.max_steps == 1
    done = managed.execute_model_job(
        runner, provider(ScriptedModel(defect=False)), owner="retry"
    )
    assert done.status == "succeeded"
    assert (
        runner.get_run(run.run_id).quality_executions[-1].command_id == "retry-quality"
    )
    assert runner.get_command(run.run_id, accepted.command_id).status == "cancelled"


def test_independent_worker_process_executes_quality_without_local_model_injection(
    tmp_path,
):
    import os
    import subprocess
    import sys

    from test_composition import ROOT

    runner, run = ready_quality(tmp_path)
    accepted = managed_quality.submit_quality(runner, run.run_id, command(runner, run))
    script = """import sys, json, httpx
from deliveryflow_contracts.model_tasks import ModelTaskInput
from deliveryflow_speccraft.providers import DeepSeekProvider
from test_quality_cycle import ScriptedModel
from apps.worker import __main__ as worker
original=DeepSeekProvider.__init__
model=ScriptedModel()
def respond(req):
    task=ModelTaskInput.model_validate_json(json.loads(req.content)["messages"][1]["content"])
    return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":json.dumps(model.execute(task))}}]})
def init(self,config):original(self,config,client=httpx.Client(transport=httpx.MockTransport(respond)))
DeepSeekProvider.__init__=init
sys.argv=["worker","--once","--database",sys.argv[1]]
worker.main()
"""
    env = {
        **os.environ,
        "SPECCRAFT_PROVIDER": "deepseek",
        "SPECCRAFT_MODEL": config().binding.model,
        "DEEPSEEK_API_KEY": "test-only-not-a-real-key",
        "PYTHONPATH": str(ROOT) + os.pathsep + str(ROOT / "tests"),
    }
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "runs.sqlite3")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "succeeded"
    assert runner.get_run(run.run_id).quality_audit_current
    assert runner.get_command(run.run_id, accepted.command_id).domain_committed

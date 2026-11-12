"""First background vertical: capture -> durable task -> candidate -> human Gate."""

import httpx
import pytest
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft import managed
from deliveryflow_speccraft.composition import build_runner
from deliveryflow_speccraft.providers import DeepSeekProvider
from deliveryflow_speccraft.runner import FakeProvider, GovernanceError
from deliveryflow_speccraft.workflow import RunWorkflow
from test_composition import ROOT
from test_provider_adapter import config


def setup(tmp_path):
    runner = build_runner(ROOT, database_path=tmp_path / "runs.sqlite3")
    return runner, managed.ManagedRunService(runner, config().binding)


def request():
    return CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")


def http_model(status=200):
    def handle(req):
        import json

        from deliveryflow_contracts.model_tasks import ModelTaskInput

        body = json.loads(req.content)
        task = ModelTaskInput.model_validate_json(body["messages"][1]["content"])
        result = FakeProvider().propose_clarifications(task)
        return httpx.Response(
            status,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": result.model_dump_json(),
                        },
                    }
                ]
            },
        )

    return DeepSeekProvider(
        config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )


def test_create_never_calls_model_and_worker_stops_with_candidates_not_facts(tmp_path):
    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    run = runner.get_run(accepted.run_id)
    assert run.status == "context_preparing" and run.available_commands == ()
    assert run.clarification_batch is None and run.ledger.facts == ()
    assert runner.get_model_budget(run.run_id).model_calls == 0
    done = managed.execute_clarification_job(runner, http_model(), owner="test-worker")
    assert done.status == "succeeded"
    current = runner.get_run(run.run_id)
    assert current.status == "awaiting_clarification"
    assert current.clarification_batch.proposals
    assert current.ledger.facts == () and current.prd_draft is None
    assert not current.completeness.is_complete
    assert runner.get_command(run.run_id, accepted.command_id).status == "succeeded"
    assert (
        managed.execute_clarification_job(runner, http_model(), owner="test-worker")
        is None
    )


def test_graph_startup_and_read_skip_managed_runs_and_legacy_write_is_closed(tmp_path):
    _runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    restarted = build_runner(ROOT, database_path=tmp_path / "runs.sqlite3")
    graph = RunWorkflow(restarted)
    assert graph.get_run(accepted.run_id).status == "context_preparing"
    assert restarted.get_model_budget(accepted.run_id).model_calls == 0
    assert graph.pending_gate(accepted.run_id) is None
    with pytest.raises(GovernanceError) as error:
        graph._apply(
            accepted.run_id, lambda: pytest.fail("must not execute legacy writes")
        )
    assert error.value.code == "execution_mode_conflict"


def test_provider_auth_failure_persists_diagnosis_without_candidate_or_success(
    tmp_path,
):
    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    failed = managed.execute_clarification_job(
        runner, http_model(401), owner="test-worker"
    )
    assert failed.status == "failed" and failed.error_code == "provider_auth_failed"
    run = runner.get_run(accepted.run_id)
    assert run.status == "context_preparing" and run.clarification_batch is None
    assert run.ledger.facts == () and run.prd_draft is None
    receipt = runner.get_command(run.run_id, accepted.command_id)
    assert receipt.status == "failed" and receipt.error_code == "provider_auth_failed"


def test_creation_queue_failure_rolls_back_run_binding_budget_receipt_and_task(
    tmp_path,
):
    runner, service = setup(tmp_path)
    runner._runs._connection.execute(
        "CREATE TRIGGER fail_queue BEFORE INSERT ON model_jobs "
        "BEGIN SELECT RAISE(ABORT, 'queue failed'); END"
    )
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError, match="queue failed"):
        service.create_run(request())
    assert runner.list_run_ids() == ()
    for table in (
        "model_budgets",
        "run_provider_bindings",
        "command_receipts",
        "model_jobs",
        "run_events",
    ):
        assert (
            runner._runs._connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            == 0
        )


def test_candidate_commit_failure_leaves_no_batch_and_restart_reuses_remaining_budget(
    tmp_path,
):
    import sqlite3

    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    before = runner.get_run(accepted.run_id)
    runner._runs._connection.execute(
        "CREATE TRIGGER fail_commit BEFORE INSERT ON run_events "
        "WHEN NEW.event_type='job.finished' BEGIN SELECT RAISE(ABORT, 'commit failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="commit failed"):
        managed.execute_clarification_job(runner, http_model(), owner="test-worker")
    assert runner.get_run(accepted.run_id) == before
    assert runner.get_command(accepted.run_id, accepted.command_id).status == "accepted"
    assert accepted.command_id not in runner._runs.commands[accepted.run_id]
    assert runner.get_model_budget(accepted.run_id).model_calls == 1
    runner._runs._connection.execute("DROP TRIGGER fail_commit")
    runner._runs._connection.execute(
        "UPDATE model_jobs SET lease_until=0 WHERE job_id=?", (accepted.job_id,)
    )
    restarted = build_runner(ROOT, database_path=tmp_path / "runs.sqlite3")
    result = managed.execute_clarification_job(
        restarted, http_model(), owner="new-worker"
    )
    assert result.status == "succeeded"
    assert restarted.get_model_budget(accepted.run_id).model_calls == 2
    assert restarted.get_run(accepted.run_id).ledger.facts == ()


def test_corrupt_provider_profile_fails_closed_instead_of_becoming_legacy(tmp_path):
    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    graph = RunWorkflow(runner)
    runner._runs._connection.execute(
        "UPDATE run_provider_bindings SET payload='{}' WHERE run_id=?",
        (accepted.run_id,),
    )
    with pytest.raises(GovernanceError) as error:
        graph._apply(
            accepted.run_id, lambda: pytest.fail("corrupt profile must close writes")
        )
    assert error.value.code == "execution_profile_invalid"
    assert runner.get_model_budget(accepted.run_id).model_calls == 0


def test_cancel_racing_with_error_recording_does_not_kill_worker_or_overwrite_cancel(
    tmp_path,
    monkeypatch,
):
    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    store = runner._runs
    original = store.fail_job

    def cancel_then_record_failure(lease, code):
        # Force a second actor's cancellation between the error and its failure transaction.
        store.cancel_job(lease.job_id)
        return original(lease, code)

    monkeypatch.setattr(store, "fail_job", cancel_then_record_failure)
    result = managed.execute_clarification_job(
        runner, http_model(401), owner="test-worker"
    )
    assert result.status == "cancelled"
    assert (
        runner.get_command(accepted.run_id, accepted.command_id).status == "cancelled"
    )
    assert runner.get_run(accepted.run_id).clarification_batch is None

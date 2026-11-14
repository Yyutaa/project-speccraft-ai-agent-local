"""Explicit cancellation/retry never replays user decisions or resets Run consumption."""

import sqlite3

import httpx
import pytest
from deliveryflow_contracts import execution as contracts
from deliveryflow_speccraft import managed
from deliveryflow_speccraft.runner import GovernanceError
from test_managed_prd import author, ready, submission


def control(runner, run_id, command_id="control-1"):
    return contracts.ManagedJobControlRequest(
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(run_id).run_version,
        command_id=command_id,
        actor_claim="reviewer",
        rationale="明确处理后台执行",
        user_confirmed=True,
    )


def failed_prd(tmp_path):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(
        runner, author(lambda _: httpx.Response(401)), owner="failing"
    )
    return runner, service, run.run_id, accepted


def test_retry_preserves_decisions_and_old_receipt_and_uses_same_task_and_remaining_run_budget(
    tmp_path,
):
    runner, service, run_id, failed = failed_prd(tmp_path)
    before = runner.get_run(run_id)
    assert runner.get_job_summary(run_id, failed.job_id).available_commands == (
        "retry_execution",
    )
    retried = service.retry_job(run_id, failed.job_id, control(runner, run_id))
    assert retried.job_id != failed.job_id
    assert runner.get_run(run_id) == before
    assert (
        runner._runs.get_job(retried.job_id).task
        == runner._runs.get_job(failed.job_id).task
    )
    assert runner.get_model_budget(run_id).model_calls == 2
    managed.execute_model_job(runner, author(), owner="retry-worker")
    assert runner.get_run(run_id).ledger == before.ledger
    assert runner.get_run(run_id).prd_draft is not None
    assert runner.get_model_budget(run_id).model_calls == 3
    original = runner.get_command(run_id, failed.command_id)
    assert original.status == "failed" and original.domain_committed is True


def test_cancellation_keeps_decisions_and_blocks_late_worker_before_model_call(
    tmp_path,
):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    before = runner.get_run(run.run_id)
    lease = runner._runs.claim_next("slow-worker")
    cancelled = service.cancel_job(
        run.run_id, accepted.job_id, control(runner, run.run_id)
    )
    assert (
        cancelled.receipt.status == "succeeded"
        and cancelled.receipt.domain_committed is True
    )
    original = runner.get_command(run.run_id, accepted.command_id)
    assert original.status == "cancelled" and original.domain_committed is True
    result = managed.execute_model_job(
        runner, author(), owner="slow-worker", claimed=lease
    )
    assert result.status == "cancelled"
    assert runner.get_run(run.run_id) == before
    assert runner.get_model_budget(run.run_id).model_calls == 1


def test_cancel_repeated_payload_and_payload_conflict_do_not_change_terminal_state(
    tmp_path,
):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    command = control(runner, run.run_id)
    service.cancel_job(run.run_id, accepted.job_id, command)
    before = runner.get_snapshot(run.run_id)
    for changed, code in (
        (command, "duplicate_command"),
        (
            command.model_copy(update={"rationale": "different"}),
            "command_payload_conflict",
        ),
    ):
        with pytest.raises(GovernanceError) as error:
            service.cancel_job(run.run_id, accepted.job_id, changed)
        assert error.value.code == code
        assert runner.get_snapshot(run.run_id) == before


def test_retry_is_not_available_after_success_or_for_another_runs_job(tmp_path):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="author")
    assert runner.get_job_summary(run.run_id, accepted.job_id).available_commands == ()
    before = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError) as error:
        service.retry_job(run.run_id, accepted.job_id, control(runner, run.run_id))
    assert error.value.code == "execution_control_unavailable"
    assert runner.get_snapshot(run.run_id) == before
    with pytest.raises(KeyError):
        service.retry_job("another-run", accepted.job_id, control(runner, run.run_id))


def test_exhausted_run_budget_cannot_be_reset_by_explicit_retry(tmp_path):
    runner, service, run_id, failed = failed_prd(tmp_path)
    runner._runs._connection.execute(
        "UPDATE model_budgets SET calls=32 WHERE run_id=?", (run_id,)
    )
    before = runner.get_snapshot(run_id)
    assert runner.get_job_summary(run_id, failed.job_id).available_commands == ()
    with pytest.raises(GovernanceError) as error:
        service.retry_job(run_id, failed.job_id, control(runner, run_id))
    assert error.value.code == "execution_control_unavailable"
    assert runner.get_snapshot(run_id) == before


def test_stale_cancel_and_failed_cancel_event_write_leave_no_command_or_job_change(
    tmp_path,
):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    command = control(runner, run.run_id)
    before = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError) as error:
        service.cancel_job(
            run.run_id,
            accepted.job_id,
            command.model_copy(update={"expected_run_version": 0}),
        )
    assert error.value.code == "run_version_conflict"
    assert runner.get_snapshot(run.run_id) == before
    runner._runs._connection.execute(
        "CREATE TRIGGER fail_cancel BEFORE INSERT ON run_events "
        "WHEN NEW.event_type='job.cancelled' BEGIN SELECT RAISE(ABORT, 'cancel failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="cancel failed"):
        service.cancel_job(run.run_id, accepted.job_id, command)
    assert runner.get_snapshot(run.run_id) == before
    assert runner._runs.get_job(accepted.job_id).status == "queued"
    with pytest.raises(KeyError):
        runner.get_command(run.run_id, command.command_id)


def test_old_receipt_json_reads_without_inventing_domain_commit(tmp_path):
    runner, _, run = ready(tmp_path)
    receipt = runner._runs.jobs_for_run(run.run_id)[0]
    import json

    stored = runner.get_command(run.run_id, receipt.command_id).model_dump(mode="json")
    stored.pop("domain_committed")
    stored.pop("actor_claim")
    stored.pop("rationale")
    runner._runs._connection.execute(
        "UPDATE command_receipts SET payload=? WHERE run_id=? AND command_id=?",
        (
            json.dumps(stored),
            run.run_id,
            receipt.command_id,
        ),
    )
    restored = runner.get_command(run.run_id, receipt.command_id)
    assert restored.domain_committed is False
    assert restored.actor_claim is None and restored.rationale is None
    assert runner.get_run(run.run_id) == run


def test_control_responsibility_survives_restart_with_receipt(tmp_path):
    runner, service, run_id, failed = failed_prd(tmp_path)
    command = control(runner, run_id, "traceable-retry")
    accepted = service.retry_job(run_id, failed.job_id, command)
    from deliveryflow_speccraft.composition import build_runner
    from test_composition import ROOT

    restarted = build_runner(ROOT, database_path=tmp_path / "runs.sqlite3")
    receipt = restarted.get_command(run_id, accepted.command_id)
    assert receipt.actor_claim == "reviewer"
    assert receipt.rationale == "明确处理后台执行"

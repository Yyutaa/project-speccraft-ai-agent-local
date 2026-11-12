"""Durable task ownership and commit boundary, independently of any model semantics."""

import json
import sqlite3
import subprocess
import sys

import pytest
from deliveryflow_contracts.runs import AvailableCommand
from deliveryflow_speccraft import execution_store
from deliveryflow_speccraft.providers import DeepSeekConfig
from test_model_boundary import prd_task
from test_runtime_store import created


def queued(tmp_path):
    path, _, run = created(tmp_path)
    store = execution_store.ExecutionStore(path)
    binding = DeepSeekConfig.from_environment(
        {
            "SPECCRAFT_PROVIDER": "deepseek",
            "SPECCRAFT_MODEL": "configured-model",
            "DEEPSEEK_API_KEY": "test-secret",
        }
    ).binding
    store.bind_provider(run.run_id, binding)
    job = store.enqueue_command_task(
        run.run_id,
        "cmd-1",
        AvailableCommand.SUBMIT_CLARIFICATION,
        {"governance_contract_version": 2},
        prd_task(),
        expected_version=store.snapshot(run.run_id).run_version,
    )
    return path, store, run, job


def test_accepted_receipt_task_and_events_commit_atomically_and_restart(tmp_path):
    path, store, run, job = queued(tmp_path)
    assert job.status == "queued" and job.epoch == 0
    assert store.get_command(run.run_id, "cmd-1").status == "accepted"
    assert store[run.run_id] == run
    assert execution_store.ExecutionStore(path).get_job(job.job_id) == job
    assert "test-secret" not in store.get_provider_binding(run.run_id).model_dump_json()
    before = store.snapshot(run.run_id)
    with pytest.raises(ValueError, match="duplicate_command"):
        store.enqueue_command_task(
            run.run_id,
            "cmd-1",
            AvailableCommand.SUBMIT_CLARIFICATION,
            {"governance_contract_version": 2},
            prd_task(),
            expected_version=2,
        )
    assert store.snapshot(run.run_id) == before


def test_enqueue_event_failure_leaves_no_receipt_or_job(tmp_path):
    _, store, run, job = queued(tmp_path)
    store.cancel_job(job.job_id)
    store._connection.execute(
        "CREATE TRIGGER fail_job BEFORE INSERT ON run_events "
        "WHEN NEW.event_type='job.queued' BEGIN SELECT RAISE(ABORT, 'queue failed'); END"
    )
    before = store.snapshot(run.run_id)
    with pytest.raises(sqlite3.IntegrityError, match="queue failed"):
        store.enqueue_command_task(
            run.run_id,
            "cmd-2",
            AvailableCommand.SUBMIT_CLARIFICATION,
            {},
            prd_task(),
            expected_version=before.run_version,
        )
    with pytest.raises(KeyError):
        store.get_command(run.run_id, "cmd-2")
    assert store.snapshot(run.run_id) == before
    assert len(store.jobs_for_run(run.run_id)) == 1


def test_second_active_job_is_rejected_without_consuming_command(tmp_path):
    _, store, run, _ = queued(tmp_path)
    with pytest.raises(ValueError, match="run_execution_busy"):
        store.enqueue_command_task(
            run.run_id,
            "cmd-2",
            AvailableCommand.SUBMIT_CLARIFICATION,
            {},
            prd_task(),
            expected_version=store.snapshot(run.run_id).run_version,
        )
    with pytest.raises(KeyError):
        store.get_command(run.run_id, "cmd-2")


def test_two_real_processes_claim_only_once(tmp_path):
    path, store, _, job = queued(tmp_path)
    code = (
        "import sys; from pathlib import Path; "
        "from deliveryflow_speccraft.execution_store import ExecutionStore; "
        "s=ExecutionStore(Path(sys.argv[1])); j=s.claim_next(sys.argv[2]); "
        "print(j.model_dump_json() if j else 'null')"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(path), owner],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for owner in ("worker-a", "worker-b")
    ]
    try:
        results = [process.communicate(timeout=10) for process in processes]
        assert [process.returncode for process in processes] == [0, 0], results
        claims = [json.loads(out) for out, _ in results]
        assert len([claim for claim in claims if claim]) == 1
        winner = next(claim for claim in claims if claim)
        assert winner["job_id"] == job.job_id and winner["epoch"] == 1
        assert store.get_job(job.job_id).status == "running"
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def expire(store, job):
    store._connection.execute(
        "UPDATE model_jobs SET lease_until=0 WHERE job_id=?", (job.job_id,)
    )


def test_expired_owner_cannot_renew_commit_fail_or_charge_after_takeover(tmp_path):
    path, store, run, job = queued(tmp_path)
    old = store.claim_next("worker-old")
    assert old is not None
    expire(store, job)
    new_store = execution_store.ExecutionStore(path)
    current = new_store.claim_next("worker-new")
    assert current and current.epoch == old.epoch + 1
    before = new_store.snapshot(run.run_id)
    for operation in (
        lambda: store.renew_lease(old),
        lambda: store.complete_job(old, run),
        lambda: store.fail_job(old, "provider_timeout"),
        lambda: store.reserve_job_call(old),
    ):
        with pytest.raises(ValueError, match="execution_lease_lost"):
            operation()
    assert new_store.snapshot(run.run_id) == before
    assert store.renew_lease(current).lease_until >= current.lease_until
    assert new_store.snapshot(run.run_id) == before


def test_cancel_invalidates_inflight_owner_but_preserves_run_and_call_consumption(
    tmp_path,
):
    path, store, run, job = queued(tmp_path)
    owned = store.claim_next("worker")
    call = store.reserve_job_call(owned)
    cancelled = execution_store.ExecutionStore(path).cancel_job(job.job_id)
    assert cancelled.status == "cancelled"
    with pytest.raises(ValueError, match="execution_lease_lost"):
        store.complete_job(owned, run)
    assert store[run.run_id] == run
    assert store.model_budget(run.run_id).model_calls == 1
    assert store.model_calls(run.run_id)[0].call_id == call.call_id
    assert store.model_calls(run.run_id)[0].status == "interrupted"
    assert store.get_command(run.run_id, "cmd-1").status == "cancelled"
    assert store.claim_next("another") is None


def test_payload_conflict_prevents_stale_model_result_commit(tmp_path):
    _, store, run, _ = queued(tmp_path)
    owned = store.claim_next("worker")
    # An independently committed authority change invalidates this task, even if its lease lives.
    changed = run.model_copy(
        update={
            "clarification_batch": run.clarification_batch.model_copy(
                update={"batch_id": "new-batch", "revision": 2},
            )
        }
    )
    store[run.run_id] = changed
    with pytest.raises(ValueError, match="execution_input_stale"):
        store.complete_job(owned, run)
    assert store[run.run_id] == changed


def test_commit_event_failure_rolls_back_run_job_receipt_and_success_id(tmp_path):
    _, store, run, job = queued(tmp_path)
    owned = store.claim_next("worker")
    call = store.reserve_job_call(owned)
    store.finish_job_call(owned, call.call_id, "succeeded")
    before = store.snapshot(run.run_id)
    store._connection.execute(
        "CREATE TRIGGER fail_finish BEFORE INSERT ON run_events "
        "WHEN NEW.event_type='job.finished' BEGIN SELECT RAISE(ABORT, 'commit failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="commit failed"):
        store.complete_job(owned, run)
    assert store.snapshot(run.run_id) == before
    assert store.get_job(job.job_id).status == "running"
    assert store.get_command(run.run_id, "cmd-1").status == "accepted"
    assert "cmd-1" not in store.commands[run.run_id]
    assert store.model_budget(run.run_id).model_calls == 1
    store._connection.execute("DROP TRIGGER fail_finish")
    done = store.complete_job(owned, run)
    assert done.status == "succeeded"
    assert "cmd-1" in store.commands[run.run_id]
    assert store.get_command(run.run_id, "cmd-1").status == "succeeded"
    with pytest.raises(ValueError, match="execution_lease_lost"):
        store.complete_job(owned, run)


def test_provider_profile_is_frozen_across_restart(tmp_path):
    path, store, run, _ = queued(tmp_path)
    profile = store.get_provider_binding(run.run_id)
    restarted = execution_store.ExecutionStore(path)
    with pytest.raises(ValueError, match="provider_binding_conflict"):
        restarted.bind_provider(
            run.run_id, profile.model_copy(update={"model": "other"})
        )
    assert restarted.get_provider_binding(run.run_id) == profile


def test_interrupted_call_is_not_refunded_on_reclaim(tmp_path):
    path, store, run, job = queued(tmp_path)
    old = store.claim_next("worker-old")
    store.reserve_job_call(old)
    expire(store, job)
    current = execution_store.ExecutionStore(path).claim_next("worker-new")
    assert current.epoch == 2
    assert store.model_calls(run.run_id)[0].status == "interrupted"
    assert store.model_budget(run.run_id).model_calls == 1


def test_v3_upgrade_is_atomic_and_does_not_invent_jobs_or_profiles(
    tmp_path, monkeypatch
):
    path, _, run = created(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE IF EXISTS model_jobs")
    connection.execute("DROP TABLE IF EXISTS run_provider_bindings")
    connection.execute("PRAGMA user_version=3")
    connection.close()
    from deliveryflow_speccraft.persistence import RunStore

    original = RunStore._migrate_execution_tables

    def fail(self):
        original(self)
        raise RuntimeError("migration failure")

    monkeypatch.setattr(RunStore, "_migrate_execution_tables", fail)
    with pytest.raises(RuntimeError, match="migration failure"):
        execution_store.ExecutionStore(path)
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 3
    assert (
        check.execute(
            "SELECT name FROM sqlite_master WHERE name='model_jobs'"
        ).fetchone()
        is None
    )
    check.close()
    monkeypatch.setattr(RunStore, "_migrate_execution_tables", original)
    store = execution_store.ExecutionStore(path)
    assert store[run.run_id] == run and store.jobs_for_run(run.run_id) == ()
    with pytest.raises(ValueError, match="provider_binding_missing"):
        store.get_provider_binding(run.run_id)

"""Multi-call quality jobs keep their execution limits across process restart."""

import sqlite3

import pytest
from deliveryflow_contracts.model_tasks import ModelResources
from deliveryflow_contracts.runs import AvailableCommand
from deliveryflow_speccraft.execution_store import ExecutionStore
from deliveryflow_speccraft.quality_engine import make_task
from test_provider_adapter import config
from test_quality_cycle import ScriptedModel, awaiting, request, subject


def queued_quality(tmp_path):
    path = tmp_path / "quality.sqlite3"
    runner = subject(ScriptedModel(), path)
    run = awaiting(runner)
    store = runner._runs
    store.bind_provider(run.run_id, config().binding)
    resources = ModelResources(
        template=runner._td_pack.template,
        guide=runner._td_pack.guide,
        self_check=runner._td_pack.self_check,
    )
    task = make_task(run, "discover", resources)
    command = request(run, steps=1)
    job = store.enqueue_command_task(
        run.run_id,
        command.command_id,
        AvailableCommand.RUN_TD_QUALITY,
        command.model_dump(mode="json"),
        task,
        expected_version=store.snapshot(run.run_id).run_version,
        quality_request=command,
    )
    return path, runner, job, resources


def test_quality_request_persists_and_actual_subtasks_are_metered(tmp_path):
    path, runner, job, resources = queued_quality(tmp_path)
    store = runner._runs
    lease = store.claim_next("worker")
    run = runner.get_run(job.run_id)
    task = make_task(run, "final_audit", resources)
    # One-step batch: (discover + final + repair + verify) * two HTTP attempts.
    for _ in range(8):
        call = store.reserve_job_call(lease, task=task)
        assert call.input_binding == task.input_binding
        store.finish_job_call(lease, call.call_id, "failed")
    with pytest.raises(ValueError, match="job_model_budget_exhausted"):
        store.reserve_job_call(lease, task=task)
    store.close()
    restored = ExecutionStore(path)
    assert restored.get_job(job.job_id).quality_request.max_steps == 1
    assert restored.model_budget(job.run_id).model_calls == 8
    assert restored._connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_v4_migration_reads_old_jobs_without_inventing_quality_request(tmp_path):
    path, runner, job, _ = queued_quality(tmp_path)
    runner._runs.close()
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE model_jobs DROP COLUMN quality_request")
    old.execute("PRAGMA user_version=4")
    old.commit()
    old.close()
    restored = ExecutionStore(path)
    assert restored.get_job(job.job_id).quality_request is None
    assert restored._connection.execute("PRAGMA user_version").fetchone()[0] == 5


def test_failed_v5_migration_is_atomic(tmp_path, monkeypatch):
    path, runner, _, _ = queued_quality(tmp_path)
    runner._runs.close()
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE model_jobs DROP COLUMN quality_request")
    old.execute("PRAGMA user_version=4")
    old.commit()
    old.close()
    original = ExecutionStore._migrate_quality_jobs

    def fail(self):
        original(self)
        raise RuntimeError("migration interrupted")

    monkeypatch.setattr(ExecutionStore, "_migrate_quality_jobs", fail)
    with pytest.raises(RuntimeError, match="migration interrupted"):
        ExecutionStore(path)
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 4
    assert "quality_request" not in [
        r[1] for r in check.execute("PRAGMA table_info(model_jobs)")
    ]

"""Process entry validates config; the heartbeat uses its own SQLite connection."""

import os
import subprocess
import sys
import time

from deliveryflow_speccraft import worker
from deliveryflow_speccraft.execution_store import ExecutionStore
from test_execution_store import expire, queued


def test_worker_missing_config_exits_without_dumping_environment(tmp_path):
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "SPECCRAFT_PROVIDER",
            "SPECCRAFT_MODEL",
            "DEEPSEEK_API_KEY",
        )
    }
    environment["UNRELATED_PRIVATE_VALUE"] = "never-print-private-value"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.worker",
            "--once",
            "--database",
            str(tmp_path / "db"),
        ],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "DEEPSEEK_API_KEY" in result.stderr
    assert "never-print-private-value" not in result.stdout + result.stderr


def test_heartbeat_renews_from_independent_connection_and_stops(tmp_path):
    path, store, _, job = queued(tmp_path)
    lease = store.claim_next("test-owner", lease_seconds=1)
    # Small timing interval is selected only by this mechanism test.
    with worker.renew_while_running(path, lease, interval_seconds=0.02):
        deadline = time.monotonic() + 2
        while store.get_job(job.job_id).lease_until <= lease.lease_until:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    after = store.get_job(job.job_id).lease_until
    time.sleep(0.05)
    assert store.get_job(job.job_id).lease_until == after
    assert ExecutionStore(path).claim_next("competitor") is None
    expire(store, job)
    assert ExecutionStore(path).claim_next("after-crash").epoch == 2


def test_crashed_process_keeps_budget_and_new_worker_process_recovers_to_human_gate(
    tmp_path,
):
    from test_managed_clarification import request, setup

    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    path = tmp_path / "runs.sqlite3"
    die = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os,sys; from pathlib import Path; "
                "from deliveryflow_speccraft.execution_store import ExecutionStore; "
                "s=ExecutionStore(Path(sys.argv[1])); j=s.claim_next('crashing-worker'); "
                "s.reserve_job_call(j); os._exit(17)"
            ),
            str(path),
        ],
        check=False,
        capture_output=True,
        timeout=10,
    )
    assert die.returncode == 17
    assert runner.get_model_budget(accepted.run_id).model_calls == 1
    runner._runs._connection.execute(
        "UPDATE model_jobs SET lease_until=0 WHERE job_id=?", (accepted.job_id,)
    )
    # Real process and production entry/HTTP adapter, vendor network isolated at MockTransport.
    environment = dict(
        os.environ,
        SPECCRAFT_PROVIDER="deepseek",
        SPECCRAFT_MODEL="configured-model",
        DEEPSEEK_API_KEY="test-secret-never-disclose",
    )
    code = (
        "import sys; sys.path.insert(0,'tests'); "
        "from test_managed_clarification import http_model; "
        "from apps.worker import __main__ as cli; "
        "cli.DeepSeekProvider=lambda config: http_model(); "
        "sys.argv=['worker','--once','--database',sys.argv[1]]; cli.main()"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert done.returncode == 0, done.stderr
    assert '"status": "succeeded"' in done.stdout
    assert "test-secret" not in done.stdout + done.stderr
    run = runner.get_run(accepted.run_id)
    assert run.status == "awaiting_clarification" and run.ledger.facts == ()
    assert runner.get_model_budget(run.run_id).model_calls == 2
    assert [c.status for c in runner._runs.model_calls(run.run_id)] == [
        "interrupted",
        "succeeded",
    ]

"""Every HTTP attempt is charged durably and fenced before/after network work."""

import httpx
import pytest
from deliveryflow_speccraft import execution
from deliveryflow_speccraft.execution_store import ExecutionStore
from deliveryflow_speccraft.persistence import ModelBudgetError, RunStore
from deliveryflow_speccraft.providers import DeepSeekProvider, ProviderError
from test_execution_store import expire, queued
from test_provider_adapter import completion, config


def model(handler, settings=None):
    return DeepSeekProvider(
        settings or config(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_retry_is_charged_before_each_request_and_success_is_only_a_candidate(tmp_path):
    path, store, run, job = queued(tmp_path)
    lease = store.claim_next("worker")
    seen = []

    def handler(_):
        read = RunStore(path)
        # A separate connection can write during model I/O: no long authority transaction.
        read._connection.execute("PRAGMA busy_timeout=100")
        read.reserve_candidate(run.run_id, "test-independent-writer", "issue", "a" * 64)
        seen.append(read.model_budget(run.run_id).model_calls)
        if len(seen) == 1:
            return httpx.Response(429, text="private server error")
        return httpx.Response(200, json=completion(job.task))

    result = execution.invoke_job_model(
        store, lease, model(handler), retry_delay_seconds=0
    )
    assert result.content is not None
    assert seen == [1, 2]
    assert [call.status for call in store.model_calls(run.run_id)] == [
        "failed",
        "succeeded",
    ]
    assert store[run.run_id] == run and store.get_job(job.job_id).status == "running"
    assert store.get_command(run.run_id, job.command_id).status == "accepted"


def test_authentication_failure_is_not_retried_and_never_returns_empty_success(
    tmp_path,
):
    _, store, run, _ = queued(tmp_path)
    lease = store.claim_next("worker")
    with pytest.raises(ProviderError, match="provider_auth_failed"):
        execution.invoke_job_model(
            store,
            lease,
            model(lambda _: httpx.Response(401)),
            retry_delay_seconds=0,
        )
    assert store.model_budget(run.run_id).model_calls == 1
    assert store.model_calls(run.run_id)[0].status == "failed"
    assert store[run.run_id] == run


def test_run_cap_blocks_second_http_attempt_after_transient_failure(tmp_path):
    _, store, run, _ = queued(tmp_path)
    # Fixture-only frozen pilot policy of one request; no production policy mutation API.
    store._connection.execute(
        "UPDATE model_budgets SET policy=? WHERE run_id=?",
        ('{"policy_version":1,"max_model_calls":1,"max_candidates":8}', run.run_id),
    )
    lease = store.claim_next("worker")
    with pytest.raises(ModelBudgetError, match="run_model_budget_exhausted"):
        execution.invoke_job_model(
            store,
            lease,
            model(lambda _: httpx.Response(503)),
            retry_delay_seconds=0,
        )
    assert store.model_budget(run.run_id).model_calls == 1


def test_restart_and_lease_takeover_preserve_per_job_attempt_limit(tmp_path):
    path, store, run, job = queued(tmp_path)
    old = store.claim_next("worker-old")
    store.reserve_job_call(
        old
    )  # Process died after reserving: request transmission is uncertain.
    expire(store, job)
    restarted = ExecutionStore(path)
    lease = restarted.claim_next("worker-new")
    with pytest.raises(ValueError, match="job_model_budget_exhausted"):
        execution.invoke_job_model(
            restarted,
            lease,
            model(lambda _: httpx.Response(503)),
            retry_delay_seconds=0,
        )
    assert store.model_budget(run.run_id).model_calls == 2
    assert [call.status for call in store.model_calls(run.run_id)] == [
        "interrupted",
        "failed",
    ]


def test_cancel_during_network_discards_result_and_retains_spent_budget(tmp_path):
    path, store, run, job = queued(tmp_path)
    lease = store.claim_next("worker")

    def cancel(_):
        ExecutionStore(path).cancel_job(job.job_id)
        return httpx.Response(200, json=completion(job.task))

    with pytest.raises(ValueError, match="execution_lease_lost"):
        execution.invoke_job_model(store, lease, model(cancel), retry_delay_seconds=0)
    assert store[run.run_id] == run
    assert store.get_command(run.run_id, job.command_id).status == "cancelled"
    assert store.model_budget(run.run_id).model_calls == 1
    assert store.model_calls(run.run_id)[0].status == "interrupted"


def test_profile_change_blocks_before_reserving_budget_or_sending_request(tmp_path):
    _, store, run, _ = queued(tmp_path)
    lease = store.claim_next("worker")
    with pytest.raises(ProviderError, match="provider_binding_conflict"):
        execution.invoke_job_model(
            store,
            lease,
            model(
                lambda _: pytest.fail("must not send HTTP on profile mismatch"),
                config(SPECCRAFT_MODEL="other-model"),
            ),
        )
    assert store.model_budget(run.run_id).model_calls == 0

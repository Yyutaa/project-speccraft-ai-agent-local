"""Decisions commit once; PRD generation is a separately recoverable consequence."""

import json
import sqlite3

import httpx
import pytest
from deliveryflow_contracts import execution as contracts
from deliveryflow_contracts.model_tasks import ModelTaskInput
from deliveryflow_speccraft import managed
from deliveryflow_speccraft.composition import build_runner
from deliveryflow_speccraft.prd_authoring import FakePrdAuthor
from deliveryflow_speccraft.providers import DeepSeekProvider
from deliveryflow_speccraft.runner import GovernanceError
from deliveryflow_speccraft.workflow import RunWorkflow
from governance_helpers import clarification_request
from test_composition import ROOT
from test_managed_clarification import http_model, request, setup
from test_provider_adapter import config


def ready(tmp_path):
    runner, service = setup(tmp_path)
    accepted = service.create_run(request())
    managed.execute_clarification_job(runner, http_model(), owner="clarifier")
    run = runner.get_run(accepted.run_id)
    return runner, service, run


def submission(runner, run, command_id="clarify-to-prd"):
    return contracts.ManagedClarificationRequest(
        execution_contract_version=1,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        request=clarification_request(run, command_id),
    )


def author(handler=None):
    def handle(req):
        task = ModelTaskInput.model_validate_json(
            json.loads(req.content)["messages"][1]["content"]
        )
        assert task.task_kind == "prd_author"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": FakePrdAuthor().author(task).model_dump_json(),
                        },
                    }
                ]
            },
        )

    return DeepSeekProvider(
        config(), client=httpx.Client(transport=httpx.MockTransport(handler or handle))
    )


def test_submission_commits_decisions_without_author_then_one_call_reaches_prd_gate(
    tmp_path,
    monkeypatch,
):
    runner, service, run = ready(tmp_path)

    class ForbiddenInlineAuthor:
        def author(self, task):
            pytest.fail("API must not call Author, including unmetered Fake preflight")

    monkeypatch.setattr(runner, "_prd_author", ForbiddenInlineAuthor())
    command = submission(runner, run)
    accepted = service.submit_clarification(run.run_id, command)
    preparing = runner.get_run(run.run_id)
    assert preparing.status == "prd_preparing" and preparing.prd_draft is None
    assert preparing.ledger.revision == run.ledger.revision + 1
    assert preparing.completeness.is_complete
    assert command.request.command_id in runner._runs.commands[run.run_id]
    assert (
        accepted.receipt.status == "accepted"
        and accepted.receipt.domain_committed is True
    )
    assert (
        runner.get_model_budget(run.run_id).model_calls == 1
    )  # Only initial clarification.
    result = managed.execute_model_job(runner, author(), owner="author")
    assert result.status == "succeeded"
    current = runner.get_run(run.run_id)
    assert current.status == "prd_awaiting_approval" and current.prd_readiness.ready
    assert current.prd_draft.revision == 1 and len(current.prd_revisions) == 1
    assert current.prd_approval is None and current.td_draft is None
    assert current.ledger == preparing.ledger
    assert runner.get_model_budget(run.run_id).model_calls == 2
    assert (
        runner.get_command(run.run_id, command.request.command_id).domain_committed
        is True
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ({}, "duplicate_command"),
        ({"rationale": "different intent"}, "command_payload_conflict"),
    ],
)
def test_repeated_request_is_recognized_before_gate_check_without_reapplying_decisions(
    tmp_path, change, code
):
    runner, service, run = ready(tmp_path)
    command = submission(runner, run)
    service.submit_clarification(run.run_id, command)
    baseline = runner.get_snapshot(run.run_id)
    repeated = command.model_copy(
        update={"request": command.request.model_copy(update=change)}
    )
    with pytest.raises(GovernanceError) as error:
        service.submit_clarification(run.run_id, repeated)
    assert error.value.code == code
    assert runner.get_snapshot(run.run_id) == baseline
    assert len(runner._runs.jobs_for_run(run.run_id)) == 2


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("expected_revision", 999, "revision_conflict"),
        ("batch_revision", 999, "clarification_batch_conflict"),
        ("source_reviews", (), "source_review_required"),
        ("answers", (), "invalid_clarification"),
    ],
)
def test_invalid_decisions_do_not_consume_command_budget_or_write_evidence(
    tmp_path, field, value, code
):
    runner, service, run = ready(tmp_path)
    baseline = runner.get_snapshot(run.run_id)
    command = submission(runner, run)
    command = command.model_copy(
        update={"request": command.request.model_copy(update={field: value})}
    )
    with pytest.raises(GovernanceError) as error:
        service.submit_clarification(run.run_id, command)
    assert error.value.code == code
    assert runner.get_snapshot(run.run_id) == baseline
    with pytest.raises(KeyError):
        runner.get_command(run.run_id, command.request.command_id)


def test_old_run_version_refuses_submission_without_any_changes(tmp_path):
    runner, service, run = ready(tmp_path)
    command = submission(runner, run).model_copy(update={"expected_run_version": 0})
    baseline = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError) as error:
        service.submit_clarification(run.run_id, command)
    assert error.value.code == "run_version_conflict"
    assert runner.get_snapshot(run.run_id) == baseline


def test_queue_failure_rolls_back_decisions_receipt_success_id_and_events(tmp_path):
    runner, service, run = ready(tmp_path)
    baseline = runner.get_snapshot(run.run_id)
    command = submission(runner, run)
    runner._runs._connection.execute(
        "CREATE TRIGGER fail_prd BEFORE INSERT ON model_jobs "
        "BEGIN SELECT RAISE(ABORT, 'queue failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="queue failure"):
        service.submit_clarification(run.run_id, command)
    assert runner.get_snapshot(run.run_id) == baseline
    assert command.request.command_id not in runner._runs.commands[run.run_id]
    with pytest.raises(KeyError):
        runner.get_command(run.run_id, command.request.command_id)


def test_provider_failure_keeps_explicit_decisions_but_never_a_draft_or_approval(
    tmp_path,
):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    before = runner.get_run(run.run_id)
    result = managed.execute_model_job(
        runner, author(lambda _: httpx.Response(401)), owner="author"
    )
    assert result.status == "failed" and result.error_code == "provider_auth_failed"
    assert runner.get_run(run.run_id) == before
    receipt = runner.get_command(run.run_id, accepted.command_id)
    assert receipt.status == "failed" and receipt.domain_committed is True
    assert runner.get_model_budget(run.run_id).model_calls == 2


def test_result_commit_failure_and_restart_preserve_ledger_budget_and_recover_remaining_attempt(
    tmp_path,
):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    before = runner.get_run(run.run_id)
    runner._runs._connection.execute(
        "CREATE TRIGGER fail_result BEFORE INSERT ON run_events WHEN NEW.event_type='job.finished' "
        "BEGIN SELECT RAISE(ABORT, 'result failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="result failure"):
        managed.execute_model_job(runner, author(), owner="author")
    assert runner.get_run(run.run_id) == before
    assert runner.get_command(run.run_id, accepted.command_id).status == "accepted"
    assert runner.get_model_budget(run.run_id).model_calls == 2
    runner._runs._connection.execute("DROP TRIGGER fail_result")
    runner._runs._connection.execute(
        "UPDATE model_jobs SET lease_until=0 WHERE job_id=?", (accepted.job_id,)
    )
    restarted = build_runner(ROOT, database_path=tmp_path / "runs.sqlite3")
    graph = RunWorkflow(restarted)
    assert graph.get_run(run.run_id) == before
    assert (
        restarted.get_model_budget(run.run_id).model_calls == 2
    )  # Reads/startup cannot generate.
    result = managed.execute_model_job(restarted, author(), owner="recovered")
    assert result.status == "succeeded"
    assert restarted.get_run(run.run_id).ledger == before.ledger
    assert restarted.get_model_budget(run.run_id).model_calls == 3


@pytest.mark.parametrize(
    "update",
    [
        {"input_binding": "0" * 64},
        {"cited_ids": ["invented-fact"]},
        {"approval": "model-approved"},
    ],
)
def test_invalid_prd_output_cannot_leave_revision_or_approval(tmp_path, update):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    before = runner.get_run(run.run_id)

    def invalid(req):
        task = ModelTaskInput.model_validate_json(
            json.loads(req.content)["messages"][1]["content"]
        )
        candidate = FakePrdAuthor().author(task).model_dump(mode="json") | update
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(candidate),
                        },
                    }
                ]
            },
        )

    result = managed.execute_model_job(runner, author(invalid), owner="invalid-author")
    assert result.status == "failed" and result.error_code == "model_output_invalid"
    assert runner.get_run(run.run_id) == before
    assert runner.get_model_budget(run.run_id).model_calls == 2


def test_cancel_during_prd_computation_discards_late_body_and_preserves_confirmed_facts(
    tmp_path,
):
    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    before = runner.get_run(run.run_id)
    from test_managed_prd_controls import control

    def cancel(req):
        task = ModelTaskInput.model_validate_json(
            json.loads(req.content)["messages"][1]["content"]
        )
        service.cancel_job(run.run_id, accepted.job_id, control(runner, run.run_id))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": FakePrdAuthor().author(task).model_dump_json(),
                        },
                    }
                ]
            },
        )

    result = managed.execute_model_job(runner, author(cancel), owner="late-author")
    assert result.status == "cancelled"
    assert runner.get_run(run.run_id) == before
    assert runner.get_model_budget(run.run_id).model_calls == 2
    assert runner._runs.model_calls(run.run_id)[-1].status == "interrupted"


def test_different_authoring_resources_refuse_stored_task_before_network(
    tmp_path, monkeypatch
):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    from dataclasses import replace

    monkeypatch.setattr(
        runner, "_prd_pack", replace(runner._prd_pack, guide="updated server rules")
    )
    result = managed.execute_model_job(
        runner,
        author(lambda _: pytest.fail("stale task must not call model")),
        owner="changed-resources",
    )
    assert result.status == "failed" and result.error_code == "execution_input_stale"
    assert runner.get_model_budget(run.run_id).model_calls == 1
    assert runner.get_run(run.run_id).prd_draft is None


def test_prd_worker_in_real_process_stops_before_approval(tmp_path):
    import os
    import subprocess
    import sys

    runner, service, run = ready(tmp_path)
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    code = (
        "import sys; sys.path.insert(0,'tests'); from test_managed_prd import author; "
        "from apps.worker import __main__ as cli; cli.DeepSeekProvider=lambda config: author(); "
        "sys.argv=['worker','--once','--database',sys.argv[1]]; cli.main()"
    )
    environment = dict(
        os.environ,
        SPECCRAFT_PROVIDER="deepseek",
        SPECCRAFT_MODEL="configured-model",
        DEEPSEEK_API_KEY="test-secret-never-disclose",
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "runs.sqlite3")],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert '"status": "succeeded"' in result.stdout
    assert "test-secret" not in result.stdout + result.stderr
    current = runner.get_run(run.run_id)
    assert current.status == "prd_awaiting_approval" and current.prd_approval is None
    assert runner.get_command(run.run_id, accepted.command_id).status == "succeeded"
    assert runner.get_model_budget(run.run_id).model_calls == 2


def test_exhausted_budget_stops_prd_without_erasing_submitted_decisions(tmp_path):
    runner, service, run = ready(tmp_path)
    runner._runs._connection.execute(
        "UPDATE model_budgets SET calls=32 WHERE run_id=?", (run.run_id,)
    )
    accepted = service.submit_clarification(run.run_id, submission(runner, run))
    before = runner.get_run(run.run_id)
    result = managed.execute_model_job(
        runner,
        author(lambda _: pytest.fail("must not exceed budget")),
        owner="no-budget",
    )
    assert (
        result.status == "failed" and result.error_code == "run_model_budget_exhausted"
    )
    assert runner.get_run(run.run_id) == before and before.completeness.is_complete
    assert runner.get_command(run.run_id, accepted.command_id).domain_committed is True
    assert runner.get_model_budget(run.run_id).model_calls == 32

from deliveryflow_contracts import execution as contracts
from deliveryflow_speccraft import managed
from test_managed_prd import author, ready, submission


def test_approval_is_durable_before_td_model_call(tmp_path):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="prd")
    run = runner.get_run(run.run_id)
    command = contracts.ManagedPrdApprovalRequest(
        execution_contract_version=1,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id="approve-prd",
        request={
            "governance_contract_version": 2,
            "revision": run.prd_draft.revision,
            "content_hash": run.prd_draft.content_hash,
            "actor": "human",
            "rationale": "reviewed",
        },
    )
    accepted = service.approve_prd(run.run_id, command)
    current = runner.get_run(run.run_id)
    assert current.status == "td_preparing"
    assert current.prd_approval.actor == "human"
    assert current.td_draft is None
    assert accepted.receipt.domain_committed


def approved(tmp_path):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="prd")
    run = runner.get_run(run.run_id)
    command = contracts.ManagedPrdApprovalRequest(
        execution_contract_version=1,
        expected_run_version=runner.get_snapshot(run.run_id).run_version,
        command_id="approve-prd",
        request={
            "governance_contract_version": 2,
            "revision": run.prd_draft.revision,
            "content_hash": run.prd_draft.content_hash,
            "actor": "human",
            "rationale": "reviewed",
        },
    )
    accepted = service.approve_prd(run.run_id, command)
    return runner, service, command, accepted


def td_provider(status=200):
    import json

    import httpx
    from deliveryflow_contracts.model_tasks import ModelTaskInput
    from deliveryflow_speccraft.providers import DeepSeekProvider
    from deliveryflow_speccraft.td_authoring import FakeTdAuthor
    from test_provider_adapter import config

    def handle(req):
        if status != 200:
            return httpx.Response(status)
        task = ModelTaskInput.model_validate_json(
            json.loads(req.content)["messages"][1]["content"]
        )
        assert task.task_kind == "td_author"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": FakeTdAuthor().author(task).model_dump_json(),
                        },
                    }
                ]
            },
        )

    return DeepSeekProvider(
        config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )


def test_td_worker_stops_at_independent_human_review(tmp_path):
    runner, _, command, accepted = approved(tmp_path)
    before = runner.get_run(accepted.run_id)
    result = managed.execute_model_job(runner, td_provider(), owner="td")
    assert result.status == "succeeded"
    current = runner.get_run(accepted.run_id)
    assert current.status == "td_awaiting_approval"
    assert current.prd_approval == before.prd_approval
    assert current.td_draft and current.td_approval is None
    assert current.prd_draft.content_hash == command.request.content_hash
    assert current.td_review.status == "missing"


def test_td_provider_failure_preserves_human_approval(tmp_path):
    runner, _, _, accepted = approved(tmp_path)
    before = runner.get_run(accepted.run_id)
    result = managed.execute_model_job(runner, td_provider(401), owner="td")
    assert result.status == "failed"
    assert runner.get_run(accepted.run_id) == before
    receipt = runner.get_command(accepted.run_id, accepted.command_id)
    assert receipt.domain_committed and receipt.actor_claim == "human"


def test_duplicate_approval_does_not_queue_or_call_again(tmp_path):
    import pytest
    from deliveryflow_speccraft.runner import GovernanceError

    runner, service, command, accepted = approved(tmp_path)
    before = runner.get_snapshot(accepted.run_id)
    with pytest.raises(GovernanceError, match="duplicate_command"):
        service.approve_prd(accepted.run_id, command)
    assert runner.get_snapshot(accepted.run_id) == before


def test_technical_decisions_commit_then_new_td_job(tmp_path):
    import json

    import httpx
    from deliveryflow_contracts.model_tasks import ModelTaskInput
    from deliveryflow_speccraft.providers import DeepSeekProvider
    from test_provider_adapter import config
    from test_td_runner import DecisionAuthor

    runner, service, _, accepted = approved(tmp_path)

    def handle(req):
        task = ModelTaskInput.model_validate_json(
            json.loads(req.content)["messages"][1]["content"]
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": DecisionAuthor().author(task).model_dump_json(),
                        },
                    }
                ]
            },
        )

    provider = DeepSeekProvider(
        config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    assert (
        managed.execute_model_job(runner, provider, owner="questions").status
        == "succeeded"
    )
    waiting = runner.get_run(accepted.run_id)
    assert waiting.status == "td_awaiting_decision"
    command = contracts.ManagedTechnicalDecisionsRequest(
        execution_contract_version=1,
        governance_contract_version=2,
        expected_run_version=runner.get_snapshot(waiting.run_id).run_version,
        command_id="decide-storage",
        actor_claim="human",
        rationale="local deployment",
        user_confirmed=True,
        request={
            "governance_contract_version": 2,
            "expected_prd_revision": waiting.prd_draft.revision,
            "expected_prd_content_hash": waiting.prd_draft.content_hash,
            "decisions": [
                {"request_id": "tech-storage", "answer": "local", "actor": "human"}
            ],
        },
    )
    service.submit_technical_decisions(waiting.run_id, command)
    preparing = runner.get_run(waiting.run_id)
    assert preparing.status == "td_preparing" and preparing.technical_decisions
    assert preparing.prd_approval == waiting.prd_approval
    assert managed.execute_model_job(runner, provider, owner="td").status == "succeeded"
    assert runner.get_run(waiting.run_id).status == "td_awaiting_approval"
    assert runner.get_model_budget(waiting.run_id).model_calls == 4


def test_td_enqueue_failure_rolls_back_approval_and_authority(tmp_path):
    import sqlite3

    import pytest

    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="prd")
    run = runner.get_run(run.run_id)
    baseline = runner.get_snapshot(run.run_id)
    command = contracts.ManagedPrdApprovalRequest(
        execution_contract_version=1,
        expected_run_version=baseline.run_version,
        command_id="approve",
        request={
            "governance_contract_version": 2,
            "revision": run.prd_draft.revision,
            "content_hash": run.prd_draft.content_hash,
            "actor": "human",
            "rationale": "reviewed",
        },
    )
    runner._runs._connection.execute(
        "CREATE TRIGGER fail_td BEFORE INSERT ON model_jobs BEGIN SELECT RAISE(ABORT, 'queue failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="queue failure"):
        service.approve_prd(run.run_id, command)
    assert runner.get_snapshot(run.run_id) == baseline
    assert runner.get_run(run.run_id).prd_approval is None

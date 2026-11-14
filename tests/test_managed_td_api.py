import pytest
from deliveryflow_speccraft import managed
from deliveryflow_speccraft.runner import InvalidTechnicalDecision, PrdNotReady
from test_managed_prd import author, ready, submission
from test_managed_prd_api import client_for
from test_managed_td import approved


def prd_command(runner, run):
    return {
        "execution_contract_version": 1,
        "expected_run_version": runner.get_snapshot(run.run_id).run_version,
        "command_id": "approve-api",
        "request": {
            "governance_contract_version": 2,
            "revision": run.prd_draft.revision,
            "content_hash": run.prd_draft.content_hash,
            "actor": "human",
            "rationale": "reviewed",
        },
    }


@pytest.mark.parametrize(
    "change,code",
    [
        ({"revision": 999}, "revision_conflict"),
        ({"content_hash": "0" * 64}, "content_hash_conflict"),
    ],
)
def test_approval_stale_binding_returns_409_without_writes(
    tmp_path, monkeypatch, change, code
):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="prd")
    run = runner.get_run(run.run_id)
    command = prd_command(runner, run)
    command["request"].update(change)
    before = runner.get_snapshot(run.run_id)
    response = client_for(runner, monkeypatch).post(
        f"/api/managed/runs/{run.run_id}/prd/approve", json=command
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == code
    assert runner.get_snapshot(run.run_id) == before


def test_unready_prd_returns_stable_error(tmp_path, monkeypatch):
    runner, service, run = ready(tmp_path)
    service.submit_clarification(run.run_id, submission(runner, run))
    managed.execute_model_job(runner, author(), owner="prd")
    run = runner.get_run(run.run_id)

    def unready(*args):
        raise PrdNotReady("unready")

    monkeypatch.setattr(runner, "prepare_prd_approval", unready)
    response = client_for(runner, monkeypatch).post(
        f"/api/managed/runs/{run.run_id}/prd/approve", json=prd_command(runner, run)
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "prd_not_ready"
    )


def technical_command(runner, run):
    return {
        "execution_contract_version": 1,
        "governance_contract_version": 2,
        "expected_run_version": runner.get_snapshot(run.run_id).run_version,
        "command_id": "technical-api",
        "actor_claim": "human",
        "rationale": "reviewed",
        "user_confirmed": True,
        "request": {
            "governance_contract_version": 2,
            "expected_prd_revision": run.prd_draft.revision,
            "expected_prd_content_hash": run.prd_draft.content_hash,
            "decisions": [
                {"request_id": "storage", "answer": "invalid", "actor": "human"}
            ],
        },
    }


def test_invalid_technical_decision_returns_stable_error(tmp_path, monkeypatch):
    runner, _, _, accepted = approved(tmp_path)
    run = runner.get_run(accepted.run_id)

    def invalid(*args):
        raise InvalidTechnicalDecision("not an offered option")

    monkeypatch.setattr(runner, "prepare_technical_decisions", invalid)
    response = client_for(runner, monkeypatch).post(
        f"/api/managed/runs/{run.run_id}/technical-decisions",
        json=technical_command(runner, run),
    )
    assert (
        response.status_code == 422
        and response.json()["detail"]["code"] == "invalid_technical_decision"
    )


def test_nested_decision_actor_conflict_refused_before_business_call(
    tmp_path, monkeypatch
):
    runner, _, _, accepted = approved(tmp_path)
    run = runner.get_run(accepted.run_id)
    command = technical_command(runner, run)
    command["request"]["decisions"][0]["actor"] = "another"
    before = runner.get_snapshot(run.run_id)
    response = client_for(runner, monkeypatch).post(
        f"/api/managed/runs/{run.run_id}/technical-decisions", json=command
    )
    assert (
        response.status_code == 422
        and response.json()["detail"]["code"] == "command_identity_conflict"
    )
    assert runner.get_snapshot(run.run_id) == before


def test_technical_option_guard_is_atomic(tmp_path):
    from deliveryflow_contracts.execution import ManagedTechnicalDecisionsRequest
    from deliveryflow_contracts.runs import AvailableCommand, RunStatus
    from deliveryflow_contracts.td import AuthorityTopic, TechnicalDecisionRequest
    from deliveryflow_speccraft.runner import GovernanceError

    runner, service, _, accepted = approved(tmp_path)
    run = runner.get_run(accepted.run_id)
    # Seed the legitimate waiting projection while retaining the authoritative frozen PRD.
    runner._runs.cancel_job(accepted.job_id)
    waiting = runner._validated_update(
        run,
        {
            "status": RunStatus.TD_AWAITING_DECISION,
            "technical_decision_requests": (
                TechnicalDecisionRequest(
                    request_id="storage",
                    topic=AuthorityTopic.DATA,
                    question="Storage?",
                    options=("local", "object"),
                    reason="explicit choice",
                ),
            ),
            "available_commands": (AvailableCommand.SUBMIT_TECHNICAL_DECISIONS,),
        },
    )
    runner._runs[run.run_id] = waiting
    command = ManagedTechnicalDecisionsRequest.model_validate(
        technical_command(runner, waiting)
    )
    before = runner.get_snapshot(run.run_id)
    with pytest.raises(GovernanceError, match="invalid_technical_decision"):
        service.submit_technical_decisions(run.run_id, command)
    assert runner.get_snapshot(run.run_id) == before


def test_service_revalidates_unchecked_approval_wrapper(tmp_path):
    from pydantic import ValidationError

    _runner, service, command, accepted = approved(tmp_path)
    invalid = command.model_copy(update={"execution_contract_version": 99})
    with pytest.raises(ValidationError):
        service.approve_prd(accepted.run_id, invalid)

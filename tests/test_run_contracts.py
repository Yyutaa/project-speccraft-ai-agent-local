import hashlib
from pathlib import Path

import pytest
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import InMemoryRunner
from governance_helpers import clarification_request
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent


def waiting():
    runner = InMemoryRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
    )
    return runner, runner.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="需求",
        )
    )


def ready():
    runner, run = waiting()
    return runner.submit_clarification(run.run_id, clarification_request(run))


def test_create_run_request_preserves_raw_requirement_and_rejects_blank_text() -> None:
    request = CreateRunRequest(
        governance_contract_version=2, requirement="  导出大文件时显示进度。  "
    )
    assert request.requirement == "  导出大文件时显示进度。  "
    with pytest.raises(ValidationError):
        CreateRunRequest(governance_contract_version=2, requirement=" \n ")


def test_prd_waiting_run_has_revision_and_approval_commands() -> None:
    run = ready()
    assert run.available_commands == ("revise_prd", "approve_prd")
    assert run.td_draft is None
    assert run.prd_approval is None
    assert run.delivery_spec is None


def test_completed_run_requires_both_approvals_and_delivery_spec() -> None:
    run = ready()
    with pytest.raises(ValidationError):
        RunResponse.model_validate(
            {**run.model_dump(), "status": "completed", "available_commands": ()}
        )


def test_waiting_for_clarification_has_questions_but_no_prd() -> None:
    _, run = waiting()
    assert run.prd_draft is None
    assert not run.completeness.is_complete
    assert run.available_commands == ("submit_clarification",)
    assert run.ledger.facts == ()


def test_waiting_for_clarification_cannot_include_a_prd_draft() -> None:
    _, run = waiting()
    draft = ready().prd_draft
    with pytest.raises(ValidationError):
        RunResponse.model_validate({**run.model_dump(), "prd_draft": draft})


def test_run_rejects_fact_evidence_not_bound_to_a_captured_source() -> None:
    run = ready()
    payload = run.model_dump()
    fact = payload["ledger"]["facts"][0]
    fact["source"]["sha256"] = hashlib.sha256(b"unrelated source").hexdigest()
    fact["source"]["excerpt"] = "not from this snapshot"
    with pytest.raises(ValidationError, match="precise admission evidence"):
        RunResponse.model_validate(payload)

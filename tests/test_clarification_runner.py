from pathlib import Path

import pytest
from deliveryflow_contracts.facts import (
    FactKind,
    SubmitClarificationRequest,
)
from deliveryflow_contracts.runs import CreateRunRequest, RunStatus
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import (
    DuplicateCommand,
    InMemoryRunner,
    InvalidClarification,
    RevisionConflict,
)
from governance_helpers import clarification_request


def make_runner() -> InMemoryRunner:
    root = Path(__file__).parent.parent / "examples/speccraft/repositories/exportflow-sample"
    pack = Path(__file__).parent.parent / "learning-assets/authoring-pack/v1/prd"
    return InMemoryRunner(RepositoryHarness(root), pack)


def answer_all(run, command_id: str = "command-1") -> SubmitClarificationRequest:
    assert run.clarification_batch is not None
    return clarification_request(run, command_id)


def test_incomplete_source_waits_for_clarification_before_prd_exists() -> None:
    run = make_runner().create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建一个导出工具。")
    )

    assert run.status is RunStatus.AWAITING_CLARIFICATION
    assert run.prd_draft is None
    assert run.clarification_batch is not None
    assert len(run.clarification_batch.blocking_gap_ids) == 5
    assert run.available_commands == ("submit_clarification",)
    assert not any(fact.kind is FactKind.DECISION for fact in run.ledger.facts)
    assert all(proposal.recommended_option_id for proposal in run.clarification_batch.proposals)


def test_explicit_answers_create_decision_evidence_and_resume_prd_generation() -> None:
    runner = make_runner()
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建一个导出工具。")
    )

    resumed = runner.submit_clarification(waiting.run_id, answer_all(waiting))

    assert resumed.status is RunStatus.PRD_AWAITING_APPROVAL
    assert resumed.ledger.revision == waiting.ledger.revision + 1
    decisions = [fact for fact in resumed.ledger.facts if fact.kind is FactKind.DECISION]
    assert len(decisions) == 5
    assert all(fact.decision_evidence is not None for fact in decisions)
    assert resumed.completeness.is_complete
    assert resumed.prd_draft is not None
    assert "创建一个导出工具。" in resumed.prd_draft.content


def test_partial_answers_are_rejected_without_changing_the_run() -> None:
    runner = make_runner()
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建一个导出工具。")
    )
    request = answer_all(waiting).model_copy(update={"answers": answer_all(waiting).answers[:1]})

    with pytest.raises(InvalidClarification):
        runner.submit_clarification(waiting.run_id, request)

    assert runner.get_run(waiting.run_id) == waiting


def test_stale_revision_is_rejected_without_changing_the_run() -> None:
    runner = make_runner()
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建一个导出工具。")
    )
    request = answer_all(waiting).model_copy(update={"expected_revision": 2})

    with pytest.raises(RevisionConflict):
        runner.submit_clarification(waiting.run_id, request)

    assert runner.get_run(waiting.run_id) == waiting


def test_repeated_clarification_command_is_rejected_without_changing_the_run() -> None:
    runner = make_runner()
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建一个导出工具。")
    )
    request = answer_all(waiting)
    resumed = runner.submit_clarification(waiting.run_id, request)

    with pytest.raises(DuplicateCommand):
        runner.submit_clarification(waiting.run_id, request)

    assert runner.get_run(waiting.run_id) == resumed


def test_recommendation_does_not_become_a_decision_without_an_answer_command() -> None:
    runner = make_runner()
    waiting = runner.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建一个导出工具。")
    )
    assert waiting.clarification_batch is not None
    assert all(proposal.recommended_option_id for proposal in waiting.clarification_batch.proposals)

    assert not any(fact.kind is FactKind.DECISION for fact in waiting.ledger.facts)

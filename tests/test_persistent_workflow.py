import subprocess
import sys
from pathlib import Path

import pytest
from deliveryflow_contracts.model_tasks import ModelTaskOutput
from deliveryflow_contracts.prd import PrdApprovalRequest
from deliveryflow_contracts.runs import CreateRunRequest, RunStatus
from deliveryflow_contracts.td import (
    AuthorityTopic,
    SubmitTechnicalDecisionsRequest,
    TdApprovalRequest,
    TechnicalDecision,
    TechnicalDecisionRequest,
)
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import DuplicateCommand, InMemoryRunner
from deliveryflow_speccraft.td_authoring import FakeTdAuthor
from deliveryflow_speccraft.workflow import RunWorkflow, WorkflowSyncPending
from governance_helpers import clarification_request, td_review_request

ROOT = Path(__file__).parent.parent


def open_workflow(database: Path, td_author: FakeTdAuthor | None = None) -> RunWorkflow:
    runner = InMemoryRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
        database_path=database,
        td_author=td_author,
    )
    return RunWorkflow(runner)


def test_restart_restores_authoritative_run_and_gate(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    first = open_workflow(database)
    created = first.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )

    second = open_workflow(database)
    assert second.get_run(created.run_id) == created
    assert second.pending_gate(created.run_id) == "await_clarification"

    answered = second.submit_clarification(
        created.run_id, clarification_request(created, "persistent-answer")
    )
    assert answered.status is RunStatus.PRD_AWAITING_APPROVAL

    third = open_workflow(database)
    assert third.get_run(created.run_id) == answered
    assert third.pending_gate(created.run_id) == "await_prd_review"
    with pytest.raises(DuplicateCommand):
        third.submit_clarification(
            created.run_id, clarification_request(created, "persistent-answer")
        )


def test_completed_run_survives_restart_with_approvals_and_artifacts(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    first = open_workflow(database)
    created = first.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    prd = first.submit_clarification(created.run_id, clarification_request(created))
    assert prd.prd_draft is not None
    second = open_workflow(database)
    td = second.approve_prd(
        prd.run_id,
        PrdApprovalRequest(
            governance_contract_version=2,
            revision=prd.prd_draft.revision,
            content_hash=prd.prd_draft.content_hash,
            actor="product-owner",
            rationale="reviewed",
        ),
    )
    assert td.status is RunStatus.TD_AWAITING_APPROVAL
    assert td.prd_approval is not None and td.td_draft is not None
    third = open_workflow(database)
    reviewed = third.record_td_review(td.run_id, td_review_request(td))
    assert reviewed.td_review is not None
    done = third.approve_td(
        td.run_id,
        TdApprovalRequest(
            governance_contract_version=2,
            revision=td.td_draft.revision,
            content_hash=td.td_draft.content_hash,
            actor="tech-owner",
            rationale="reviewed",
            review_id=reviewed.td_review.current_review_id,
            expected_review_revision=reviewed.td_review.review_revision,
        ),
    )
    fourth = open_workflow(database)
    assert fourth.get_run(done.run_id) == done
    assert fourth.pending_gate(done.run_id) is None
    assert len(done.artifact_envelopes) == 3


def test_separate_python_process_reads_and_resumes_run(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    first = open_workflow(database)
    created = first.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    script = """
import sys
from pathlib import Path
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import InMemoryRunner
from deliveryflow_speccraft.workflow import RunWorkflow
from deliveryflow_contracts.facts import SubmitClarificationRequest

root, db, run_id, request_json = sys.argv[1:]
runner = InMemoryRunner(
    RepositoryHarness(Path(root) / 'examples/speccraft/repositories/exportflow-sample'),
    Path(root) / 'learning-assets/authoring-pack/v1/prd',
    database_path=Path(db),
)
workflow = RunWorkflow(runner)
assert workflow.pending_gate(run_id) == 'await_clarification'
updated = workflow.submit_clarification(
    run_id, SubmitClarificationRequest.model_validate_json(request_json)
)
assert updated.prd_draft is not None
print(updated.status)
"""
    result = subprocess.run(
        [
            sys.executable, "-c", script, str(ROOT), str(database), created.run_id,
            clarification_request(created).model_dump_json(),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert open_workflow(database).get_run(created.run_id).status is RunStatus.PRD_AWAITING_APPROVAL


def test_committed_command_recovers_after_graph_failure_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "runs.sqlite3"
    first = open_workflow(database)
    created = first.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    request = clarification_request(created, "crash-boundary")

    def graph_unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(first._graph, "invoke", graph_unavailable)
    with pytest.raises(WorkflowSyncPending) as error:
        first.submit_clarification(created.run_id, request)
    assert error.value.committed is True

    recovered = open_workflow(database)
    assert recovered.get_run(created.run_id).status is RunStatus.PRD_AWAITING_APPROVAL
    assert recovered.pending_gate(created.run_id) == "await_prd_review"
    with pytest.raises(DuplicateCommand):
        recovered.submit_clarification(created.run_id, request)


class DecisionAuthor(FakeTdAuthor):
    def author(self, task):  # type: ignore[no-untyped-def]
        if not task.payload.decisions:
            return ModelTaskOutput(
                task_kind="td_author",
                input_binding=task.input_binding,
                cited_ids=task.payload.blueprint.authority_ids
                + task.payload.blueprint.obligation_ids,
                decision_requests=(
                    TechnicalDecisionRequest(
                        request_id="storage",
                        topic=AuthorityTopic.DATA,
                        question="选择存储方式",
                        options=("local", "object-storage"),
                        reason="无法确定",
                    ),
                ),
            )
        return super().author(task)


def test_technical_decision_gate_survives_restart(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    first = open_workflow(database, DecisionAuthor())
    created = first.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    prd = first.submit_clarification(created.run_id, clarification_request(created))
    assert prd.prd_draft is not None
    waiting = first.approve_prd(
        prd.run_id,
        PrdApprovalRequest(
            governance_contract_version=2,
            revision=prd.prd_draft.revision,
            content_hash=prd.prd_draft.content_hash,
            actor="product-owner",
            rationale="reviewed",
        ),
    )
    assert waiting.status is RunStatus.TD_AWAITING_DECISION
    recovered = open_workflow(database, DecisionAuthor())
    assert recovered.pending_gate(waiting.run_id) == "await_technical_decision"
    updated = recovered.submit_technical_decisions(
        waiting.run_id,
        SubmitTechnicalDecisionsRequest(
            governance_contract_version=2,
            expected_prd_revision=prd.prd_draft.revision,
            expected_prd_content_hash=prd.prd_draft.content_hash,
            decisions=(TechnicalDecision(request_id="storage", answer="local", actor="tech-owner"),),
        ),
    )
    assert updated.status is RunStatus.TD_AWAITING_APPROVAL


def test_prd_generation_is_executed_by_graph_after_clarification(tmp_path: Path) -> None:
    subject = open_workflow(tmp_path / "runs.sqlite3")
    assert {"build_prd_blueprint", "generate_prd", "check_prd_readiness"} <= set(
        subject._graph.nodes
    )
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    prd = subject.submit_clarification(created.run_id, clarification_request(created))
    assert prd.status is RunStatus.PRD_AWAITING_APPROVAL
    assert prd.prd_blueprint is not None and prd.prd_draft is not None

from pathlib import Path

import pytest
from deliveryflow_contracts.facts import SubmitClarificationRequest
from deliveryflow_contracts.model_tasks import ModelTaskOutput
from deliveryflow_contracts.prd import PrdApprovalRequest, PrdRevisionRequest
from deliveryflow_contracts.runs import CreateRunRequest, RunStatus
from deliveryflow_contracts.td import (
    AuthorityTopic,
    SubmitTechnicalDecisionsRequest,
    TdApprovalRequest,
    TechnicalDecision,
    TechnicalDecisionRequest,
)
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import (
    DuplicateCommand,
    InMemoryRunner,
    RevisionConflict,
)
from deliveryflow_speccraft.td_authoring import FakeTdAuthor
from deliveryflow_speccraft.workflow import (
    RunWorkflow,
    WorkflowOutOfSync,
    WorkflowStartFailed,
    WorkflowSyncPending,
)
from governance_helpers import clarification_request, td_review_request

ROOT = Path(__file__).parent.parent


def workflow(td_author=None) -> RunWorkflow:
    runner = InMemoryRunner(
        RepositoryHarness(ROOT / "examples/speccraft/repositories/exportflow-sample"),
        ROOT / "learning-assets/authoring-pack/v1/prd",
        td_authoring_directory=ROOT / "learning-assets/authoring-pack/v1/td",
        td_author=td_author,
    )
    return RunWorkflow(runner)


def answer_request(run, command_id="answer-1") -> SubmitClarificationRequest:
    batch = run.clarification_batch
    assert batch is not None
    return clarification_request(run, command_id)


def test_create_interrupts_and_clarification_resumes_to_prd_gate() -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )

    assert subject.pending_gate(created.run_id) == "await_clarification"
    checkpoint = subject._graph.get_state(subject._config(created.run_id))
    assert checkpoint.tasks[0].interrupts
    assert set(checkpoint.values) == {"run_id", "gate", "gate_key"}
    assert created.requirement not in str(checkpoint.values)
    resumed = subject.submit_clarification(created.run_id, answer_request(created))
    assert resumed.status is RunStatus.PRD_AWAITING_APPROVAL
    assert subject.pending_gate(created.run_id) == "await_prd_review"


def test_prd_revision_reinterrupts_same_gate_then_approvals_finish() -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    prd = subject.submit_clarification(created.run_id, answer_request(created))
    assert prd.prd_draft is not None
    revised = subject.revise_prd(
        prd.run_id,
        PrdRevisionRequest(
            governance_contract_version=2,
            expected_revision=prd.prd_draft.revision,
            expected_content_hash=prd.prd_draft.content_hash,
            section_id="acceptance",
            replacement_body="用户可以看到导出进度和成功提示。",
            feedback="使结果可观察",
        ),
    )
    assert revised.prd_draft is not None
    assert revised.prd_draft.revision == 2
    assert subject.pending_gate(prd.run_id) == "await_prd_review"
    assert subject.gate_key(prd.run_id) != subject.gate_key_for(prd)

    td = subject.approve_prd(
        revised.run_id,
        PrdApprovalRequest(
            governance_contract_version=2,
            revision=revised.prd_draft.revision,
            content_hash=revised.prd_draft.content_hash,
            actor="product-owner",
            rationale="reviewed",
        ),
    )
    assert td.status is RunStatus.TD_AWAITING_APPROVAL
    assert subject.pending_gate(td.run_id) == "await_td_review"
    assert td.td_draft is not None
    old_gate_key = subject.gate_key(td.run_id)
    td = subject.record_td_review(td.run_id, td_review_request(td))
    assert subject.gate_key(td.run_id) != old_gate_key
    assert subject.pending_gate(td.run_id) == "await_td_review"
    done = subject.approve_td(
        td.run_id,
        TdApprovalRequest(
            governance_contract_version=2,
            revision=td.td_draft.revision,
            content_hash=td.td_draft.content_hash,
            actor="tech-owner",
            rationale="reviewed",
            review_id=td.td_review.current_review_id,
            expected_review_revision=td.td_review.review_revision,
        ),
    )
    assert done.status is RunStatus.COMPLETED
    assert subject.pending_gate(done.run_id) is None
    assert len(done.artifact_envelopes) == 3


class DecisionAuthor(FakeTdAuthor):
    def author(self, task):
        if not task.payload.decisions:
            return ModelTaskOutput(
                task_kind="td_author",
                input_binding=task.input_binding,
                cited_ids=task.payload.blueprint.authority_ids
                + task.payload.blueprint.obligation_ids,
                decision_requests=(
                    TechnicalDecisionRequest(
                        request_id="tech-storage",
                        topic=AuthorityTopic.DATA,
                        question="选择存储方式",
                        options=("local", "object-storage"),
                        reason="无法确定",
                    ),
                ),
            )
        return super().author(task)


def test_optional_technical_decision_gate() -> None:
    subject = workflow(DecisionAuthor())
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    prd = subject.submit_clarification(created.run_id, answer_request(created))
    assert prd.prd_draft is not None
    waiting = subject.approve_prd(
        prd.run_id,
        PrdApprovalRequest(
            governance_contract_version=2,
            revision=prd.prd_draft.revision,
            content_hash=prd.prd_draft.content_hash,
            actor="product-owner",
            rationale="reviewed",
        ),
    )
    assert subject.pending_gate(waiting.run_id) == "await_technical_decision"
    chosen = subject.submit_technical_decisions(
        waiting.run_id,
        SubmitTechnicalDecisionsRequest(
            governance_contract_version=2,
            expected_prd_revision=prd.prd_draft.revision,
            expected_prd_content_hash=prd.prd_draft.content_hash,
            decisions=(
                TechnicalDecision(
                    request_id="tech-storage", answer="local", actor="tech-owner"
                ),
            ),
        ),
    )
    assert chosen.status is RunStatus.TD_AWAITING_APPROVAL
    assert subject.pending_gate(chosen.run_id) == "await_td_review"


def test_invalid_or_duplicate_command_does_not_advance_checkpoint() -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    old_key = subject.gate_key(created.run_id)
    with pytest.raises(RevisionConflict):
        subject.submit_clarification(
            created.run_id,
            answer_request(created).model_copy(update={"expected_revision": 2}),
        )
    assert subject.gate_key(created.run_id) == old_key
    accepted = subject.submit_clarification(created.run_id, answer_request(created))
    with pytest.raises(DuplicateCommand):
        subject.submit_clarification(created.run_id, answer_request(created))
    assert subject.get_run(created.run_id) == accepted
    assert subject.pending_gate(created.run_id) == "await_prd_review"


def test_failed_graph_resume_reports_commit_then_read_reconciles(monkeypatch) -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    original = subject._graph.invoke
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("checkpoint unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(subject._graph, "invoke", fail_once)
    with pytest.raises(WorkflowSyncPending) as error:
        subject.submit_clarification(created.run_id, answer_request(created))
    assert error.value.run_id == created.run_id
    assert error.value.committed
    assert subject.get_run(created.run_id).status is RunStatus.PRD_AWAITING_APPROVAL
    assert subject.pending_gate(created.run_id) == "await_prd_review"


def test_new_process_loses_run_and_checkpoint() -> None:
    original = workflow()
    created = original.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    replacement = workflow()
    with pytest.raises(Exception, match=created.run_id):
        replacement.get_run(created.run_id)


def test_graph_fails_after_checkpoint_write_without_replaying_domain_command(
    monkeypatch,
) -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    original = subject._graph.invoke

    def write_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("response lost after checkpoint")

    monkeypatch.setattr(subject._graph, "invoke", write_then_fail)
    with pytest.raises(WorkflowSyncPending):
        subject.submit_clarification(created.run_id, answer_request(created))
    current = subject.get_run(created.run_id)
    assert current.ledger.revision == 2
    assert subject.pending_gate(created.run_id) == "await_prd_review"
    with pytest.raises(DuplicateCommand):
        subject.submit_clarification(created.run_id, answer_request(created))


def test_partial_graph_step_resumes_pure_route_without_replaying_domain_command(
    monkeypatch,
) -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    original = subject._graph.invoke

    def stop_before_route(*args, **kwargs):
        original(*args, **kwargs, interrupt_before=["route"])
        raise RuntimeError("response lost between graph nodes")

    monkeypatch.setattr(subject._graph, "invoke", stop_before_route)
    with pytest.raises(WorkflowSyncPending):
        subject.submit_clarification(created.run_id, answer_request(created))
    monkeypatch.setattr(subject._graph, "invoke", original)
    assert subject.pending_gate(created.run_id) == "route"
    assert subject.get_run(created.run_id).status is RunStatus.PRD_AWAITING_APPROVAL
    assert subject.pending_gate(created.run_id) == "await_prd_review"
    assert subject._runner.get_run(created.run_id).ledger.revision == 2


def test_partial_graph_step_before_next_gate_finishes_interrupt(monkeypatch) -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    original = subject._graph.invoke

    def stop_before_next_gate(*args, **kwargs):
        original(*args, **kwargs, interrupt_before=["await_prd_review"])
        raise RuntimeError("response lost before next interrupt")

    monkeypatch.setattr(subject._graph, "invoke", stop_before_next_gate)
    with pytest.raises(WorkflowSyncPending):
        subject.submit_clarification(created.run_id, answer_request(created))
    monkeypatch.setattr(subject._graph, "invoke", original)
    assert subject.pending_gate(created.run_id) == "await_prd_review"
    assert subject.get_run(created.run_id).status is RunStatus.PRD_AWAITING_APPROVAL
    assert subject._graph.get_state(subject._config(created.run_id)).tasks[0].interrupts


def test_unexplained_checkpoint_mismatch_blocks_writes_without_domain_change(
    monkeypatch,
) -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    monkeypatch.setattr(subject, "_is_synced", lambda run: False)
    with pytest.raises(WorkflowOutOfSync):
        subject.submit_clarification(created.run_id, answer_request(created))
    assert subject._runner.get_run(created.run_id) == created


def test_missing_existing_checkpoint_blocks_writes_without_recreating_it() -> None:
    subject = workflow()
    created = subject.create_run(
        CreateRunRequest(governance_contract_version=2, requirement="创建导出工具。")
    )
    subject._checkpointer.delete_thread(created.run_id)

    with pytest.raises(WorkflowOutOfSync):
        subject.submit_clarification(created.run_id, answer_request(created))

    assert subject._runner.get_run(created.run_id) == created
    assert subject.pending_gate(created.run_id) is None


def test_graph_start_failure_discards_unpublished_run(monkeypatch) -> None:
    subject = workflow()

    def fail_start(*args, **kwargs):
        raise RuntimeError("checkpoint unavailable")

    monkeypatch.setattr(subject._graph, "invoke", fail_start)
    with pytest.raises(WorkflowStartFailed):
        subject.create_run(
            CreateRunRequest(
                governance_contract_version=2, requirement="创建导出工具。"
            )
        )
    assert not subject._runner._runs


def test_graph_start_failure_keeps_stable_error_if_checkpoint_cleanup_fails(
    monkeypatch,
) -> None:
    subject = workflow()

    def unavailable(*args, **kwargs):
        raise RuntimeError("checkpoint unavailable")

    monkeypatch.setattr(subject._graph, "invoke", unavailable)
    monkeypatch.setattr(subject._checkpointer, "delete_thread", unavailable)
    with pytest.raises(WorkflowStartFailed):
        subject.create_run(
            CreateRunRequest(
                governance_contract_version=2, requirement="创建导出工具。"
            )
        )
    assert not subject._runner._runs

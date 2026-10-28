from pathlib import Path

import pytest
from deliveryflow_contracts.facts import ClarificationAnswer, SubmitClarificationRequest
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
from deliveryflow_speccraft.td_authoring import FakeTdAuthor, TdAuthorResult
from deliveryflow_speccraft.workflow import (
    RunWorkflow,
    WorkflowOutOfSync,
    WorkflowStartFailed,
    WorkflowSyncPending,
)

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
    return SubmitClarificationRequest(
        expected_revision=run.ledger.revision,
        command_id=command_id,
        answers=tuple(
            ClarificationAnswer(
                question_id=item.question_id,
                selected_option_id=item.options[0].option_id,
            )
            for item in batch.proposals
            if item.gap_id in batch.blocking_gap_ids
        ),
    )


def test_create_interrupts_and_clarification_resumes_to_prd_gate() -> None:
    subject = workflow()
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))

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
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
    prd = subject.submit_clarification(created.run_id, answer_request(created))
    assert prd.prd_draft is not None
    revised = subject.revise_prd(
        prd.run_id,
        PrdRevisionRequest(
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
            revision=revised.prd_draft.revision,
            content_hash=revised.prd_draft.content_hash,
            actor="product-owner",
            rationale="reviewed",
        ),
    )
    assert td.status is RunStatus.TD_AWAITING_APPROVAL
    assert subject.pending_gate(td.run_id) == "await_td_review"
    assert td.td_draft is not None
    done = subject.approve_td(
        td.run_id,
        TdApprovalRequest(
            revision=td.td_draft.revision,
            content_hash=td.td_draft.content_hash,
            actor="tech-owner",
            rationale="reviewed",
        ),
    )
    assert done.status is RunStatus.COMPLETED
    assert subject.pending_gate(done.run_id) is None
    assert len(done.artifact_envelopes) == 3


class DecisionAuthor(FakeTdAuthor):
    def author(self, blueprint, authority, obligations, pack, repository_constraints, decisions):
        if not decisions:
            return TdAuthorResult(decision_requests=(TechnicalDecisionRequest(
                request_id="tech-storage",
                topic=AuthorityTopic.DATA,
                question="选择存储方式",
                options=("local", "object-storage"),
                reason="无法确定",
            ),))
        return super().author(
            blueprint, authority, obligations, pack, repository_constraints, decisions
        )


def test_optional_technical_decision_gate() -> None:
    subject = workflow(DecisionAuthor())
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
    prd = subject.submit_clarification(created.run_id, answer_request(created))
    assert prd.prd_draft is not None
    waiting = subject.approve_prd(
        prd.run_id,
        PrdApprovalRequest(
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
            expected_prd_revision=prd.prd_draft.revision,
            expected_prd_content_hash=prd.prd_draft.content_hash,
            decisions=(TechnicalDecision(
                request_id="tech-storage", answer="local", actor="tech-owner"
            ),),
        ),
    )
    assert chosen.status is RunStatus.TD_AWAITING_APPROVAL
    assert subject.pending_gate(chosen.run_id) == "await_td_review"


def test_invalid_or_duplicate_command_does_not_advance_checkpoint() -> None:
    subject = workflow()
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
    created = original.create_run(CreateRunRequest(requirement="创建导出工具。"))
    replacement = workflow()
    with pytest.raises(Exception, match=created.run_id):
        replacement.get_run(created.run_id)


def test_graph_fails_after_checkpoint_write_without_replaying_domain_command(monkeypatch) -> None:
    subject = workflow()
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
    monkeypatch.setattr(subject, "_is_synced", lambda run: False)
    with pytest.raises(WorkflowOutOfSync):
        subject.submit_clarification(created.run_id, answer_request(created))
    assert subject._runner.get_run(created.run_id) == created


def test_missing_existing_checkpoint_blocks_writes_without_recreating_it() -> None:
    subject = workflow()
    created = subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
        subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
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
        subject.create_run(CreateRunRequest(requirement="创建导出工具。"))
    assert not subject._runner._runs

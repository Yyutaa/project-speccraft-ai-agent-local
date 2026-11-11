"""In-memory LangGraph cursor around the authoritative Run domain state."""

from collections.abc import Callable
from contextlib import suppress
from threading import RLock
from typing import NotRequired, TypedDict

from deliveryflow_contracts.facts import SubmitClarificationRequest
from deliveryflow_contracts.prd import (
    PrdApprovalRequest,
    PrdBlueprint,
    PrdReadiness,
    PrdRevision,
    PrdRevisionRequest,
)
from deliveryflow_contracts.quality import (
    QualityCycleRequest,
    QualityIssueDecisionRequest,
    QualityPatchRequest,
    QualityRiskAcceptanceRequest,
)
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse, RunStatus
from deliveryflow_contracts.td import (
    RecordTdReviewRequest,
    SubmitTechnicalDecisionsRequest,
    TdApprovalRequest,
    TdRevisionRequest,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, StateSnapshot, interrupt

from deliveryflow_speccraft.prd import build_prd_blueprint, check_prd_readiness
from deliveryflow_speccraft.runner import RunRunner


class WorkflowState(TypedDict):
    run_id: str
    gate: NotRequired[str]
    gate_key: NotRequired[str]


class WorkflowOutOfSync(Exception):
    """The checkpoint cannot be reconciled with the authoritative Run."""


class WorkflowSyncPending(Exception):
    """The domain command committed, but checkpoint advancement did not finish."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"workflow checkpoint is pending for Run {run_id}")
        self.run_id = run_id
        self.committed = True


class WorkflowStartFailed(Exception):
    """A new Run could not be given a usable checkpoint."""


GATES = {
    RunStatus.AWAITING_CLARIFICATION: "await_clarification",
    RunStatus.PRD_AWAITING_APPROVAL: "await_prd_review",
    RunStatus.TD_AWAITING_DECISION: "await_technical_decision",
    RunStatus.TD_AWAITING_APPROVAL: "await_td_review",
    RunStatus.COMPLETED: "completed",
}


class RunWorkflow:
    """Coordinates one-process domain writes with real graph interrupts."""

    def __init__(self, runner: RunRunner) -> None:
        self._runner = runner
        self._lock = RLock()
        self._pending_sync: dict[str, str] = {}
        self._prd_work: dict[str, tuple[PrdBlueprint, PrdRevision | None, PrdReadiness | None]] = {}
        self._checkpointer = InMemorySaver()

        builder = StateGraph(WorkflowState)
        builder.add_node("route", self._route)
        builder.add_node("build_prd_blueprint", self._build_prd_blueprint)
        builder.add_node("generate_prd", self._generate_prd)
        builder.add_node("check_prd_readiness", self._check_prd_readiness)
        builder.add_edge("build_prd_blueprint", "generate_prd")
        builder.add_edge("generate_prd", "check_prd_readiness")
        builder.add_edge("check_prd_readiness", "route")
        for gate in GATES.values():
            if gate != "completed":
                builder.add_node(gate, self._wait_for_user)
                builder.add_edge(gate, "route")
        builder.add_edge(START, "route")
        builder.add_conditional_edges(
            "route",
            lambda state: state["gate"],
            {
                **{gate: (END if gate == "completed" else gate) for gate in GATES.values()},
                "build_prd_blueprint": "build_prd_blueprint",
            },
        )
        self._graph = builder.compile(checkpointer=self._checkpointer)
        # A new process reconstructs only the route cursor from validated domain Runs.
        # Missing checkpoints after startup still fail closed.
        for run_id in runner.list_run_ids():
            run = runner.get_run(run_id)
            if run.status is RunStatus.PRD_PREPARING:
                self._graph.invoke({"run_id": run_id}, self._config(run_id))
                run = runner.get_run(run_id)
            self._ensure_synced(run, allow_bootstrap=True)

    @staticmethod
    def gate_key_for(run: RunResponse) -> str:
        if run.status is RunStatus.PRD_PREPARING:
            return f"{run.status}:{run.ledger.revision}"
        if run.status is RunStatus.AWAITING_CLARIFICATION:
            assert run.clarification_batch is not None
            return (
                f"{run.status}:{run.ledger.revision}:"
                f"{run.clarification_batch.batch_id}:{run.clarification_batch.revision}"
            )
        if run.status is RunStatus.PRD_AWAITING_APPROVAL:
            assert run.prd_draft is not None
            return f"{run.status}:{run.prd_draft.revision}:{run.prd_draft.content_hash}"
        if run.status is RunStatus.TD_AWAITING_DECISION:
            assert run.prd_approval is not None
            request_ids = ",".join(
                sorted(item.request_id for item in run.technical_decision_requests)
            )
            return (
                f"{run.status}:{run.prd_approval.revision}:"
                f"{run.prd_approval.content_hash}:{request_ids}"
            )
        if run.status is RunStatus.TD_AWAITING_APPROVAL:
            assert run.td_draft is not None
            assert run.td_review is not None
            return (
                f"{run.status}:{run.td_draft.revision}:{run.td_draft.content_hash}:"
                f"{run.td_review.review_revision}"
            )
        return str(run.status)

    def _route(self, state: WorkflowState) -> dict[str, str]:
        run = self._runner.get_run(state["run_id"])
        gate = "build_prd_blueprint" if run.status is RunStatus.PRD_PREPARING else GATES[run.status]
        return {"gate": gate, "gate_key": self.gate_key_for(run)}

    def _build_prd_blueprint(self, state: WorkflowState) -> dict[str, str]:
        run = self._runner.get_run(state["run_id"])
        if run.status is not RunStatus.PRD_PREPARING:
            raise WorkflowOutOfSync("PRD Blueprint step requires a preparing Run")
        self._prd_work[run.run_id] = (build_prd_blueprint(run.ledger), None, None)
        return {}

    def _generate_prd(self, state: WorkflowState) -> dict[str, str]:
        run = self._runner.get_run(state["run_id"])
        blueprint = self._prd_work[run.run_id][0]
        self._prd_work[run.run_id] = self._runner._create_prd(run.ledger, blueprint)
        return {}

    def _check_prd_readiness(self, state: WorkflowState) -> dict[str, str]:
        run_id = state["run_id"]
        blueprint, prd, readiness = self._prd_work[run_id]
        assert prd is not None and readiness is not None
        if readiness != check_prd_readiness(prd):
            raise WorkflowOutOfSync("PRD readiness changed during execution")
        self._runner.finish_prd_preparation(run_id, blueprint, prd, readiness)
        self._prd_work.pop(run_id, None)
        return {}

    @staticmethod
    def _wait_for_user(state: WorkflowState) -> dict[str, str]:
        token = interrupt(
            {
                "run_id": state["run_id"],
                "gate": state["gate"],
                "gate_key": state["gate_key"],
            }
        )
        if token != state["gate_key"]:
            raise WorkflowOutOfSync("resume token does not match interrupted Gate")
        return {}

    @staticmethod
    def _config(run_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": run_id}}

    def _snapshot(self, run_id: str) -> StateSnapshot:
        return self._graph.get_state(self._config(run_id))

    def pending_gate(self, run_id: str) -> str | None:
        snapshot = self._snapshot(run_id)
        return snapshot.next[0] if snapshot.next else None

    def gate_key(self, run_id: str) -> str | None:
        return self._snapshot(run_id).values.get("gate_key")

    def _is_synced(self, run: RunResponse) -> bool:
        snapshot = self._snapshot(run.run_id)
        gate = GATES[run.status]
        expected_next = () if gate == "completed" else (gate,)
        return (
            snapshot.values.get("run_id") == run.run_id
            and snapshot.values.get("gate") == gate
            and snapshot.values.get("gate_key") == self.gate_key_for(run)
            and snapshot.next == expected_next
            and (gate == "completed" or bool(snapshot.tasks and snapshot.tasks[0].interrupts))
        )

    def _ensure_synced(self, run: RunResponse, *, allow_bootstrap: bool = False) -> None:
        for _ in range(4):
            if self._is_synced(run):
                self._pending_sync.pop(run.run_id, None)
                return
            snapshot = self._snapshot(run.run_id)
            if not snapshot.values:
                if not allow_bootstrap:
                    raise WorkflowOutOfSync("existing Run has no graph checkpoint")
                self._graph.invoke({"run_id": run.run_id}, self._config(run.run_id))
                continue
            old_key = self._pending_sync.get(run.run_id)
            if old_key is None or snapshot.values.get("run_id") != run.run_id:
                raise WorkflowOutOfSync("checkpoint differs from authoritative Run")
            checkpoint_key = snapshot.values.get("gate_key")
            if checkpoint_key not in (old_key, self.gate_key_for(run)):
                raise WorkflowOutOfSync("checkpoint does not match pending transition")
            if snapshot.tasks and snapshot.tasks[0].interrupts:
                if checkpoint_key != old_key:
                    raise WorkflowOutOfSync("unexpected interrupted Gate")
                self._graph.invoke(Command(resume=old_key), self._config(run.run_id))
            elif snapshot.next and all(
                node in ("route", *GATES.values()) for node in snapshot.next
            ):
                self._graph.invoke(None, self._config(run.run_id))
            else:
                raise WorkflowOutOfSync("checkpoint has no recoverable route")
        raise WorkflowOutOfSync("graph did not stop at the authoritative Gate")

    def create_run(self, request: CreateRunRequest) -> RunResponse:
        with self._lock:
            run = self._runner.create_run(request)
            try:
                self._ensure_synced(run, allow_bootstrap=True)
            except Exception as error:
                self._runner.discard_unpublished_run(run.run_id)
                with suppress(Exception):
                    self._checkpointer.delete_thread(run.run_id)
                raise WorkflowStartFailed(run.run_id) from error
            return run

    def get_run(self, run_id: str) -> RunResponse:
        with self._lock:
            run = self._runner.get_run(run_id)
            if run.status is RunStatus.PRD_PREPARING:
                with suppress(Exception):
                    self._resume_preparing(run)
                return self._runner.get_run(run_id)
            with suppress(Exception):
                self._ensure_synced(run)
            # A read still returns the domain state during graph failure.
            return run

    def _resume_preparing(self, run: RunResponse) -> None:
        if run.run_id not in self._pending_sync:
            raise WorkflowOutOfSync("preparing Run has no committed transition marker")
        # No PRD has been committed. Recompute the disposable preparation steps
        # from the authoritative Ledger after a failed graph invocation.
        self._checkpointer.delete_thread(run.run_id)
        self._prd_work.pop(run.run_id, None)
        self._graph.invoke({"run_id": run.run_id}, self._config(run.run_id))
        self._ensure_synced(self._runner.get_run(run.run_id))

    def _apply(
        self,
        run_id: str,
        operation: Callable[[], RunResponse],
    ) -> RunResponse:
        with self._lock:
            before = self._runner.get_run(run_id)
            try:
                self._ensure_synced(before)
            except WorkflowOutOfSync:
                raise
            except Exception as error:
                raise WorkflowOutOfSync("checkpoint unavailable before domain command") from error
            updated = operation()
            self._pending_sync[run_id] = self.gate_key_for(before)
            try:
                if updated.status is RunStatus.PRD_PREPARING:
                    self._graph.invoke(
                        Command(resume=self.gate_key_for(before)), self._config(run_id)
                    )
                    updated = self._runner.get_run(run_id)
                self._ensure_synced(updated)
            except Exception as error:
                raise WorkflowSyncPending(run_id) from error
            return updated

    def submit_clarification(self, run_id: str, request: SubmitClarificationRequest) -> RunResponse:
        return self._apply(
            run_id,
            lambda: self._runner.submit_clarification(run_id, request, defer_prd=True),
            # PRD construction is executed by graph nodes after this domain command commits.
        )

    def revise_prd(self, run_id: str, request: PrdRevisionRequest) -> RunResponse:
        return self._apply(
            run_id,
            lambda: self._runner.revise_prd(run_id, request),
        )

    def approve_prd(self, run_id: str, request: PrdApprovalRequest) -> RunResponse:
        return self._apply(
            run_id,
            lambda: self._runner.approve_prd(run_id, request),
        )

    def submit_technical_decisions(
        self, run_id: str, request: SubmitTechnicalDecisionsRequest
    ) -> RunResponse:
        return self._apply(
            run_id,
            lambda: self._runner.submit_technical_decisions(run_id, request),
        )

    def revise_td(self, run_id: str, request: TdRevisionRequest) -> RunResponse:
        return self._apply(run_id, lambda: self._runner.revise_td(run_id, request))

    def decide_td_issue(self, run_id: str, request: QualityIssueDecisionRequest) -> RunResponse:
        return self._apply(run_id, lambda: self._runner.decide_td_issue(run_id, request))

    def run_td_quality(self, run_id: str, request: QualityCycleRequest) -> RunResponse:
        return self._apply(run_id, lambda: self._runner.run_td_quality(run_id, request))

    def patch_td_issue(self, run_id: str, request: QualityPatchRequest) -> RunResponse:
        return self._apply(run_id, lambda: self._runner.patch_td_issue(run_id, request))

    def accept_td_quality_risk(
        self, run_id: str, request: QualityRiskAcceptanceRequest
    ) -> RunResponse:
        return self._apply(run_id, lambda: self._runner.accept_td_quality_risk(run_id, request))

    def record_td_review(self, run_id: str, request: RecordTdReviewRequest) -> RunResponse:
        return self._apply(run_id, lambda: self._runner.record_td_review(run_id, request))

    def approve_td(self, run_id: str, request: TdApprovalRequest) -> RunResponse:
        return self._apply(
            run_id,
            lambda: self._runner.approve_td(run_id, request),
        )

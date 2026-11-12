import os
from pathlib import Path as FilePath
from typing import Annotated, Literal

from deliveryflow_contracts.context import HarnessErrorCode
from deliveryflow_contracts.events import RunEvent
from deliveryflow_contracts.execution import (
    CommandReceipt,
    ModelBudgetUsage,
    RunSnapshot,
)
from deliveryflow_contracts.facts import SubmitClarificationRequest
from deliveryflow_contracts.prd import PrdApprovalRequest, PrdRevisionRequest
from deliveryflow_contracts.quality import (
    QualityCycleRequest,
    QualityIssueDecisionRequest,
    QualityPatchRequest,
    QualityRiskAcceptanceRequest,
)
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_contracts.td import (
    RecordTdReviewRequest,
    SubmitTechnicalDecisionsRequest,
    TdApprovalRequest,
    TdRevisionRequest,
)
from deliveryflow_speccraft.composition import build_runner
from deliveryflow_speccraft.model_boundary import ModelBoundaryError
from deliveryflow_speccraft.repository_context import HarnessReadError
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    DuplicateCommand,
    GovernanceError,
    InvalidClarification,
    InvalidPrdRevision,
    InvalidRunTransition,
    InvalidTechnicalDecision,
    PrdNotReady,
    RevisionConflict,
    RunNotFound,
    TdObligationConflict,
)
from deliveryflow_speccraft.workflow import (
    RunWorkflow,
    WorkflowOutOfSync,
    WorkflowStartFailed,
    WorkflowSyncPending,
)
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PROJECT_ROOT = FilePath(__file__).resolve().parents[2]
runner = build_runner(
    PROJECT_ROOT,
    database_path=FilePath(
        os.environ.get(
            "SPECCRAFT_DB_PATH", PROJECT_ROOT / ".deliveryflow-state/runs.sqlite3"
        )
    ),
)
workflow = RunWorkflow(runner)
RunIdPath = Annotated[str, Path(min_length=1)]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class StageSummary(BaseModel):
    id: str
    title: str
    description: str
    implemented: bool = False


class ScaffoldResponse(BaseModel):
    project: str
    mode: Literal["project-scaffold"]
    implemented_capabilities: list[str]
    deferred_capabilities: list[str]
    stages: list[StageSummary]


STAGES = [
    StageSummary(
        id="requirement_context",
        title="需求上下文构建",
        description="建立可信来源、仓库绑定与只读工程上下文。",
    ),
    StageSummary(
        id="requirement_clarification",
        title="需求澄清与决策",
        description="发现缺口，由用户确认关键产品事实。",
    ),
    StageSummary(
        id="product_specification",
        title="产品规格设计",
        description="基于已确认事实生成 PRD。",
    ),
    StageSummary(
        id="product_approval",
        title="产品规格验收",
        description="人工修订并批准冻结 PRD。",
    ),
    StageSummary(
        id="technical_design",
        title="技术方案设计",
        description="从批准 PRD 派生技术权威并生成统一 TD。",
    ),
    StageSummary(
        id="technical_validation",
        title="技术方案验证",
        description="发现、修复并收敛技术质量问题。",
    ),
    StageSummary(
        id="technical_approval",
        title="技术方案验收",
        description="人工批准绑定确定版本的 TD。",
    ),
    StageSummary(
        id="artifact_publication",
        title="交付物发布",
        description="发布 PRD、TD 与机器可读 DeliverySpec。",
    ),
]


app = FastAPI(title="SpecCraft Project API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    if request.method == "POST" and request.url.path.startswith("/api/runs"):
        missing_version = any(
            item["type"] == "missing"
            and item["loc"] == ("body", "governance_contract_version")
            for item in error.errors()
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": (
                        "contract_version_required"
                        if missing_version
                        else "invalid_td_review"
                        if request.url.path.endswith("/td/reviews")
                        else "invalid_td_revision"
                        if request.url.path.endswith("/td/revisions")
                        else "invalid_request"
                    ),
                }
            },
        )
    return await request_validation_exception_handler(request, error)


@app.exception_handler(ModelBoundaryError)
def model_boundary_error_handler(
    request: Request, error: ModelBoundaryError
) -> JSONResponse:
    status_code = (
        413
        if error.code in ("model_context_too_large", "model_output_too_large")
        else 422
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": error.code, "committed": False}},
    )


@app.exception_handler(GovernanceError)
def governance_error_handler(request: Request, error: GovernanceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code, content={"detail": {"code": error.code}}
    )


@app.exception_handler(WorkflowSyncPending)
def workflow_sync_pending_handler(
    request: Request, error: WorkflowSyncPending
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "workflow_sync_pending",
                "run_id": error.run_id,
                "committed": error.committed,
            }
        },
    )


@app.exception_handler(WorkflowOutOfSync)
def workflow_out_of_sync_handler(
    request: Request, error: WorkflowOutOfSync
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "workflow_out_of_sync", "committed": False}},
    )


@app.exception_handler(WorkflowStartFailed)
def workflow_start_failed_handler(
    request: Request, error: WorkflowStartFailed
) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": {"code": "workflow_start_failed"}}
    )


@app.get("/api/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok", service="speccraft-project-scaffold")


@app.get("/api/scaffold", response_model=ScaffoldResponse)
def read_scaffold() -> ScaffoldResponse:
    return ScaffoldResponse(
        project="SpecCraft AI Agent",
        mode="project-scaffold",
        implemented_capabilities=[
            "React 与 FastAPI 最小链路",
            "Python 多包边界",
            "匿名需求与目标仓库样例",
            "SQLite Run、Fact Ledger、澄清 Gate 与 PRD-first 人工审批 Happy Path",
            "LangGraph 人工中断、PRD 编制节点与重启游标重建",
        ],
        deferred_capabilities=[
            "真实 LLM Provider 与模型调用",
            "完整 PRD/TD 质量 Workflow 与质量闭环",
            "Provider-driven Worker 与 Workbench",
            "Codex Native Skills 与 Host Runtime",
        ],
        stages=STAGES,
    )


@app.post("/api/runs", response_model=RunResponse, status_code=201)
def create_run(request: CreateRunRequest) -> RunResponse:
    try:
        return workflow.create_run(request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except HarnessReadError as error:
        status_code = {
            HarnessErrorCode.PATH_OUTSIDE_ROOT: 403,
            HarnessErrorCode.SYMLINK_NOT_ALLOWED: 403,
            HarnessErrorCode.PATH_NOT_ALLOWED: 403,
            HarnessErrorCode.SOURCE_NOT_FOUND: 404,
            HarnessErrorCode.FILE_TOO_LARGE: 413,
            HarnessErrorCode.CONTEXT_TOO_LARGE: 413,
            HarnessErrorCode.UNSUPPORTED_FILE: 415,
        }.get(error.code, 422)
        raise HTTPException(
            status_code=status_code, detail={"code": error.code.value}
        ) from error


@app.get("/api/runs/{run_id}", response_model=RunResponse)
def read_run(run_id: RunIdPath) -> RunResponse:
    try:
        return workflow.get_run(run_id)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found"},
        ) from error


@app.get("/api/runs/{run_id}/snapshot", response_model=RunSnapshot)
def read_run_snapshot(run_id: RunIdPath) -> RunSnapshot:
    try:
        return runner.get_snapshot(run_id)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error


@app.get("/api/runs/{run_id}/model-budget", response_model=ModelBudgetUsage)
def read_model_budget(run_id: RunIdPath) -> ModelBudgetUsage:
    try:
        return runner.get_model_budget(run_id)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error


@app.get("/api/runs/{run_id}/events", response_model=tuple[RunEvent, ...])
def read_run_events(
    run_id: RunIdPath, after: Annotated[int, Query(ge=0)] = 0,
) -> tuple[RunEvent, ...]:
    try:
        return runner.get_events(run_id, after)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error


@app.get("/api/runs/{run_id}/commands/{command_id}", response_model=CommandReceipt)
def read_command_receipt(
    run_id: RunIdPath, command_id: Annotated[str, Path(min_length=1)],
) -> CommandReceipt:
    try:
        return runner.get_command(run_id, command_id)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail={"code": "command_not_found"}) from error


@app.post(
    "/api/runs/{run_id}/clarifications/answers",
    response_model=RunResponse,
)
def submit_clarification(
    run_id: RunIdPath, request: SubmitClarificationRequest
) -> RunResponse:
    try:
        return workflow.submit_clarification(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found"},
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "revision_conflict"},
        ) from error
    except DuplicateCommand as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate_command"},
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "invalid_run_transition"},
        ) from error
    except InvalidClarification as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_clarification"},
        ) from error


@app.post("/api/runs/{run_id}/prd/revisions", response_model=RunResponse)
def revise_prd(run_id: RunIdPath, request: PrdRevisionRequest) -> RunResponse:
    try:
        return workflow.revise_prd(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_run_transition"}
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "revision_conflict"}
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except InvalidPrdRevision as error:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_prd_revision"}
        ) from error


@app.post("/api/runs/{run_id}/approvals/prd", response_model=RunResponse)
def approve_prd(run_id: RunIdPath, request: PrdApprovalRequest) -> RunResponse:
    try:
        return workflow.approve_prd(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found"},
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "invalid_run_transition"},
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "revision_conflict"},
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except PrdNotReady as error:
        raise HTTPException(
            status_code=409, detail={"code": "prd_not_ready"}
        ) from error
    except TdObligationConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "td_obligation_conflict"}
        ) from error


@app.post(
    "/api/runs/{run_id}/technical-decisions",
    response_model=RunResponse,
)
def submit_technical_decisions(
    run_id: RunIdPath, request: SubmitTechnicalDecisionsRequest
) -> RunResponse:
    try:
        return workflow.submit_technical_decisions(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_run_transition"}
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "revision_conflict"}
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except (InvalidTechnicalDecision, TdObligationConflict) as error:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_technical_decision"}
        ) from error


@app.post("/api/runs/{run_id}/approvals/td", response_model=RunResponse)
def approve_td(run_id: RunIdPath, request: TdApprovalRequest) -> RunResponse:
    try:
        return workflow.approve_td(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found"},
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "invalid_run_transition"},
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "revision_conflict"},
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except TdObligationConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "td_obligation_conflict"}
        ) from error


@app.post("/api/runs/{run_id}/td/reviews", response_model=RunResponse)
def record_td_review(run_id: RunIdPath, request: RecordTdReviewRequest) -> RunResponse:
    try:
        return workflow.record_td_review(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_run_transition"}
        ) from error
    except DuplicateCommand as error:
        raise HTTPException(
            status_code=409, detail={"code": "duplicate_command"}
        ) from error


@app.post("/api/runs/{run_id}/td/revisions", response_model=RunResponse)
def revise_td(run_id: RunIdPath, request: TdRevisionRequest) -> RunResponse:
    try:
        return workflow.revise_td(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_run_transition"}
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "revision_conflict"}
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except DuplicateCommand as error:
        raise HTTPException(
            status_code=409, detail={"code": "duplicate_command"}
        ) from error


@app.post("/api/runs/{run_id}/td/quality/decisions", response_model=RunResponse)
def decide_td_issue(run_id: RunIdPath, request: QualityIssueDecisionRequest) -> RunResponse:
    try:
        return workflow.decide_td_issue(run_id, request)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except (InvalidRunTransition, RevisionConflict, ContentHashConflict, DuplicateCommand) as error:
        codes = {InvalidRunTransition: "invalid_run_transition", RevisionConflict: "revision_conflict",
                 ContentHashConflict: "content_hash_conflict", DuplicateCommand: "duplicate_command"}
        raise HTTPException(status_code=409, detail={"code": codes[type(error)]}) from error


@app.post("/api/runs/{run_id}/td/quality/run", response_model=RunResponse)
def run_td_quality(run_id: RunIdPath, request: QualityCycleRequest) -> RunResponse:
    try:
        return workflow.run_td_quality(run_id, request)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except (InvalidRunTransition, RevisionConflict, ContentHashConflict, DuplicateCommand) as error:
        codes = {InvalidRunTransition: "invalid_run_transition", RevisionConflict: "revision_conflict",
                 ContentHashConflict: "content_hash_conflict", DuplicateCommand: "duplicate_command"}
        raise HTTPException(status_code=409, detail={"code": codes[type(error)]}) from error


@app.post("/api/runs/{run_id}/td/issues/patch", response_model=RunResponse)
def patch_td_issue(run_id: RunIdPath, request: QualityPatchRequest) -> RunResponse:
    try:
        return workflow.patch_td_issue(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_run_transition"}
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "revision_conflict"}
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except DuplicateCommand as error:
        raise HTTPException(
            status_code=409, detail={"code": "duplicate_command"}
        ) from error
    except GovernanceError as error:
        raise HTTPException(
            status_code=error.status_code, detail={"code": error.code}
        ) from error


@app.post("/api/runs/{run_id}/td/issues/accept-risk", response_model=RunResponse)
def accept_td_quality_risk(
    run_id: RunIdPath, request: QualityRiskAcceptanceRequest
) -> RunResponse:
    try:
        return workflow.accept_td_quality_risk(run_id, request)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404, detail={"code": "run_not_found"}
        ) from error
    except InvalidRunTransition as error:
        raise HTTPException(
            status_code=409, detail={"code": "invalid_run_transition"}
        ) from error
    except RevisionConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "revision_conflict"}
        ) from error
    except ContentHashConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "content_hash_conflict"}
        ) from error
    except DuplicateCommand as error:
        raise HTTPException(
            status_code=409, detail={"code": "duplicate_command"}
        ) from error
    except GovernanceError as error:
        raise HTTPException(
            status_code=error.status_code, detail={"code": error.code}
        ) from error

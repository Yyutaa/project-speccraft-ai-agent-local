from pathlib import Path as FilePath
from typing import Annotated, Literal

from deliveryflow_contracts.context import HarnessErrorCode
from deliveryflow_contracts.facts import SubmitClarificationRequest
from deliveryflow_contracts.prd import PrdApprovalRequest, PrdRevisionRequest
from deliveryflow_contracts.runs import CreateRunRequest, RunResponse
from deliveryflow_contracts.td import (
    RecordTdReviewRequest,
    SubmitTechnicalDecisionsRequest,
    TdApprovalRequest,
    TdRevisionRequest,
)
from deliveryflow_speccraft.model_boundary import ModelBoundaryError
from deliveryflow_speccraft.repository_context import (
    HarnessReadError,
    RepositoryHarness,
)
from deliveryflow_speccraft.runner import (
    ContentHashConflict,
    DuplicateCommand,
    GovernanceError,
    InMemoryRunner,
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
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PROJECT_ROOT = FilePath(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT / "examples/speccraft/repositories/exportflow-sample"
PRD_AUTHORING_ROOT = PROJECT_ROOT / "learning-assets/authoring-pack/v1/prd"
TD_AUTHORING_ROOT = PROJECT_ROOT / "learning-assets/authoring-pack/v1/td"
runner = InMemoryRunner(
    RepositoryHarness(REPOSITORY_ROOT),
    PRD_AUTHORING_ROOT,
    td_authoring_directory=TD_AUTHORING_ROOT,
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
async def invalid_request_handler(request: Request, error: RequestValidationError) -> JSONResponse:
    if request.method == "POST" and request.url.path.startswith("/api/runs"):
        missing_version = any(
            item["type"] == "missing" and item["loc"] == ("body", "governance_contract_version")
            for item in error.errors()
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": (
                        "contract_version_required" if missing_version
                        else "invalid_td_review" if request.url.path.endswith("/td/reviews")
                        else "invalid_td_revision" if request.url.path.endswith("/td/revisions")
                        else "invalid_request"
                    ),
                }
            },
        )
    return await request_validation_exception_handler(request, error)


@app.exception_handler(ModelBoundaryError)
def model_boundary_error_handler(request: Request, error: ModelBoundaryError) -> JSONResponse:
    status_code = 413 if error.code in (
        "model_context_too_large", "model_output_too_large"
    ) else 422
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": error.code, "committed": False}},
    )


@app.exception_handler(GovernanceError)
def governance_error_handler(request: Request, error: GovernanceError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": {"code": error.code}})


@app.exception_handler(WorkflowSyncPending)
def workflow_sync_pending_handler(request: Request, error: WorkflowSyncPending) -> JSONResponse:
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
def workflow_out_of_sync_handler(request: Request, error: WorkflowOutOfSync) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "workflow_out_of_sync", "committed": False}},
    )


@app.exception_handler(WorkflowStartFailed)
def workflow_start_failed_handler(request: Request, error: WorkflowStartFailed) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": {"code": "workflow_start_failed"}})


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
            "进程内存 Run、Fact Ledger、澄清 Gate 与 PRD-first 人工审批 Happy Path",
            "内存 LangGraph 人工中断与恢复",
        ],
        deferred_capabilities=[
            "真实 LLM Provider 与模型调用",
            "持久化 Run/Artifact 与跨进程恢复",
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
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
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
        raise HTTPException(status_code=status_code, detail={"code": error.code.value}) from error


@app.get("/api/runs/{run_id}", response_model=RunResponse)
def read_run(run_id: RunIdPath) -> RunResponse:
    try:
        return workflow.get_run(run_id)
    except RunNotFound as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found"},
        ) from error


@app.post(
    "/api/runs/{run_id}/clarifications/answers",
    response_model=RunResponse,
)
def submit_clarification(run_id: RunIdPath, request: SubmitClarificationRequest) -> RunResponse:
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
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except InvalidRunTransition as error:
        raise HTTPException(status_code=409, detail={"code": "invalid_run_transition"}) from error
    except RevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict"}) from error
    except ContentHashConflict as error:
        raise HTTPException(status_code=409, detail={"code": "content_hash_conflict"}) from error
    except InvalidPrdRevision as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_prd_revision"}) from error


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
        raise HTTPException(status_code=409, detail={"code": "content_hash_conflict"}) from error
    except PrdNotReady as error:
        raise HTTPException(status_code=409, detail={"code": "prd_not_ready"}) from error
    except TdObligationConflict as error:
        raise HTTPException(status_code=409, detail={"code": "td_obligation_conflict"}) from error


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
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except InvalidRunTransition as error:
        raise HTTPException(status_code=409, detail={"code": "invalid_run_transition"}) from error
    except RevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict"}) from error
    except ContentHashConflict as error:
        raise HTTPException(status_code=409, detail={"code": "content_hash_conflict"}) from error
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
        raise HTTPException(status_code=409, detail={"code": "content_hash_conflict"}) from error
    except TdObligationConflict as error:
        raise HTTPException(status_code=409, detail={"code": "td_obligation_conflict"}) from error


@app.post("/api/runs/{run_id}/td/reviews", response_model=RunResponse)
def record_td_review(run_id: RunIdPath, request: RecordTdReviewRequest) -> RunResponse:
    try:
        return workflow.record_td_review(run_id, request)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except InvalidRunTransition as error:
        raise HTTPException(status_code=409, detail={"code": "invalid_run_transition"}) from error
    except DuplicateCommand as error:
        raise HTTPException(status_code=409, detail={"code": "duplicate_command"}) from error


@app.post("/api/runs/{run_id}/td/revisions", response_model=RunResponse)
def revise_td(run_id: RunIdPath, request: TdRevisionRequest) -> RunResponse:
    try:
        return workflow.revise_td(run_id, request)
    except RunNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"}) from error
    except InvalidRunTransition as error:
        raise HTTPException(status_code=409, detail={"code": "invalid_run_transition"}) from error
    except RevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict"}) from error
    except ContentHashConflict as error:
        raise HTTPException(status_code=409, detail={"code": "content_hash_conflict"}) from error
    except DuplicateCommand as error:
        raise HTTPException(status_code=409, detail={"code": "duplicate_command"}) from error

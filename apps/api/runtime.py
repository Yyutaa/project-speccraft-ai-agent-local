"""Local supervisor telemetry, independent of authoritative Run state."""

import json
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError

router = APIRouter(prefix="/api", tags=["runtime"])


class WorkerStatus(BaseModel):
    status: Literal["running", "disabled", "stale", "exited", "unknown"] = "unknown"
    configured: bool = False
    reason: str | None = "not_supervised"
    pid: int | None = None


class RuntimeStatus(BaseModel):
    supervised: bool = False
    last_updated: float | None = None
    worker: WorkerStatus = WorkerStatus()


@router.get("/runtime")
def runtime_status() -> RuntimeStatus:
    configured = os.environ.get("SPECCRAFT_RUNTIME_STATUS_PATH")
    if not configured:
        return RuntimeStatus()
    try:
        path = Path(configured)
        if path.stat().st_size > 4096:
            return RuntimeStatus()
        status = RuntimeStatus.model_validate(json.loads(path.read_text()))
        if (
            status.last_updated is None
            or not -5 <= time.time() - status.last_updated <= 10
        ):
            status.worker.status = "stale"
            status.worker.reason = "supervisor_heartbeat_expired"
            status.worker.pid = None
        return status
    except (OSError, ValueError, ValidationError):
        return RuntimeStatus()

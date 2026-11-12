"""Notification metadata never contains document or model response bodies."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RunEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: int = Field(gt=0)
    run_id: str
    run_version: int = Field(ge=0)
    event_type: Literal[
        "run.changed",
        "model.call_reserved",
        "model.call_finished",
        "model.candidate_reserved",
        "command.accepted",
        "command.finished",
        "provider.bound",
        "job.queued",
        "job.claimed",
        "job.finished",
        "job.cancelled",
    ]
    occurred_at: datetime

"""Durable resource accounting and versioned authority reads."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.model_tasks import TaskKind
from deliveryflow_contracts.runs import AvailableCommand, RunResponse


class ModelBudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: Literal[1] = 1
    max_model_calls: int = Field(default=32, ge=1, le=4096, strict=True)
    max_candidates: int = Field(default=8, ge=1, le=1024, strict=True)


class ModelBudgetUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    policy: ModelBudgetPolicy
    model_calls: int = Field(ge=0, strict=True)
    candidates: int = Field(ge=0, strict=True)


class ModelCallRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    run_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    input_binding: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_kind: TaskKind
    status: Literal["reserved", "succeeded", "failed", "interrupted"] = "reserved"
    reserved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run: RunResponse
    run_version: int = Field(ge=0, strict=True)
    model_budget: ModelBudgetUsage | None = None


class CommandReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    kind: AvailableCommand
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["accepted", "succeeded", "failed", "cancelled"] = "accepted"
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,79}$")
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "CommandReceipt":
        if (self.status == "accepted") != (self.finished_at is None):
            raise ValueError("command outcome requires its completion time")
        if self.status == "failed" and self.error_code is None:
            raise ValueError("failed command requires a stable error code")
        if self.status in ("accepted", "succeeded") and self.error_code is not None:
            raise ValueError("successful or pending command cannot have a failure")
        return self

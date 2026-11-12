"""Durable resource accounting and versioned authority reads."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deliveryflow_contracts.model_tasks import ModelTaskInput, TaskKind
from deliveryflow_contracts.runs import AvailableCommand, CreateRunRequest, RunResponse


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


class ProviderBinding(BaseModel):
    """Public frozen execution profile. Credentials are deliberately absent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_version: Literal[1] = 1
    provider: Literal["deepseek"] = "deepseek"
    endpoint: str
    model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    max_attempts: int = Field(default=2, ge=1, le=4, strict=True)
    thinking: Literal["disabled"] = "disabled"
    max_tokens: int = Field(default=8192, ge=1, le=32768, strict=True)
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    read_timeout_seconds: float = Field(default=60.0, gt=0, le=60)
    total_timeout_seconds: float = Field(default=90.0, gt=0, le=180)


class ModelJob(BaseModel):
    """Internal execution data, never a model-controlled application command."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    task: ModelTaskInput
    baseline_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    epoch: int = Field(default=0, ge=0, strict=True)
    owner: str | None = None
    lease_until: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,79}$")

    @model_validator(mode="after")
    def validate_ownership(self) -> "ModelJob":
        if self.status == "running":
            if not self.owner or self.lease_until is None or self.epoch == 0:
                raise ValueError("running job requires ownership and a lease")
        elif self.owner is not None or self.lease_until is not None:
            raise ValueError("only running jobs can have a lease")
        if (self.status == "failed") != (self.error_code is not None):
            raise ValueError("only failed jobs require a stable failure code")
        return self


class ManagedCreateRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_contract_version: Literal[1]
    request: CreateRunRequest


class JobSummary(BaseModel):
    """Safe progress projection; excludes task input, ownership and model output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    run_id: str
    command_id: str
    task_kind: TaskKind
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    error_code: str | None = None


class ManagedRunAcceptance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    command_id: str
    job_id: str
    receipt: CommandReceipt

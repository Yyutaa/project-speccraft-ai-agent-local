"""Versioned write boundary: a client must explicitly select the governance contract."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class GovernanceWriteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    governance_contract_version: Literal[2]

    @field_validator("governance_contract_version", mode="before")
    @classmethod
    def require_explicit_version(cls, value: object) -> object:
        if type(value) is not int or value != 2:
            raise ValueError("governance contract version must be integer 2")
        return value

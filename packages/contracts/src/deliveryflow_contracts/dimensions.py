"""Shared product dimensions, independent of evidence and admission models."""

from enum import StrEnum


class FactDimension(StrEnum):
    ROLE = "role"
    WORKFLOW = "workflow"
    PERMISSION = "permission"
    FAILURE = "failure"
    ACCEPTANCE = "acceptance"

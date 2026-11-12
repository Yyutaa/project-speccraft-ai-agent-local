"""Semantic clarification candidates are external to deterministic admission."""

from typing import Protocol

from deliveryflow_contracts.model_tasks import ModelTaskInput, ModelTaskOutput


class ClarificationProvider(Protocol):
    def propose_clarifications(self, task: ModelTaskInput) -> ModelTaskOutput: ...

"""Model transport port: data-only candidates and sanitized, classifiable failures."""

from typing import Protocol

from deliveryflow_contracts.execution import ProviderBinding
from deliveryflow_contracts.model_tasks import ModelTaskInput, ModelTaskOutput


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class BoundModelProvider(Protocol):
    @property
    def binding(self) -> ProviderBinding: ...

    def execute(
        self,
        task: ModelTaskInput,
        *,
        expected_binding: ProviderBinding | None = None,
    ) -> ModelTaskOutput: ...

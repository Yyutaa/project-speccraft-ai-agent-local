"""Disposable model computation outside authority transactions; no implicit approval."""

from time import sleep

from deliveryflow_contracts.execution import ModelJob
from deliveryflow_contracts.model_tasks import ModelTaskOutput

from deliveryflow_speccraft.execution_store import ExecutionStore
from deliveryflow_speccraft.model_boundary import (
    ModelBoundaryError,
    validate_task_input,
    validate_task_output,
)
from deliveryflow_speccraft.model_provider import BoundModelProvider, ProviderError


def invoke_job_model(
    store: ExecutionStore,
    lease: ModelJob,
    provider: BoundModelProvider,
    *,
    retry_delay_seconds: float = 1.0,
) -> ModelTaskOutput:
    """Return a candidate only. Caller must recheck its lease and commit the domain result.

    Persistent per-job and per-Run limits count every reservation, including unknown
    transmission outcomes. A process restart therefore cannot reset the retry budget.
    """
    if not 0 <= retry_delay_seconds <= 10:
        raise ValueError("invalid_provider_retry_delay")
    task = validate_task_input(lease.task)
    store.require_lease(lease)
    binding = store.get_provider_binding(lease.run_id)
    if provider.binding != binding:
        raise ProviderError("provider_binding_conflict")
    while True:
        # This short transaction ends before any network operation or retry delay.
        call = store.reserve_job_call(lease)
        try:
            result = validate_task_output(
                task,
                provider.execute(task, expected_binding=binding),
            )
        except (ProviderError, ModelBoundaryError) as error:
            store.finish_job_call(lease, call.call_id, "failed")
            if isinstance(error, ProviderError) and error.retryable:
                store.require_lease(lease)
                sleep(retry_delay_seconds)
                continue
            raise
        except Exception:
            store.finish_job_call(lease, call.call_id, "failed")
            raise ProviderError("provider_unexpected_failure") from None
        store.finish_job_call(lease, call.call_id, "succeeded")
        store.require_lease(lease)
        return result

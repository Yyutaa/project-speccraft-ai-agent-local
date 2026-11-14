"""Consistent read projection for the UI; no model calls or domain mutations."""

from deliveryflow_contracts.execution import WorkbenchSnapshot
from deliveryflow_contracts.runs import AvailableCommand

from deliveryflow_speccraft.runner import RunRunner


def read_workbench(runner: RunRunner, run_id: str) -> WorkbenchSnapshot:
    store = runner._runs
    # A short read transaction shares one SQLite snapshot across Run/jobs/events.
    # No network, model operation or stream wait is allowed inside this scope.
    with store._read_scope():
        snapshot = runner.get_snapshot(run_id)
        managed = runner.is_managed_run(run_id)
        jobs = store.jobs_for_run(run_id)
        commands = snapshot.run.available_commands
        if managed and any(job.status in ("queued", "running") for job in jobs):
            commands = ()
        else:
            usage = snapshot.model_budget
            blocked: set[AvailableCommand] = set()
            if usage is None or usage.model_calls >= usage.policy.max_model_calls:
                blocked.add(AvailableCommand.RUN_TD_QUALITY)
            if usage is not None and usage.candidates >= usage.policy.max_candidates:
                blocked.add(AvailableCommand.PATCH_TD_ISSUE)
            if managed and usage is not None:
                binding = store.get_provider_binding(run_id)
                if snapshot.run.quality_provider != f"{binding.provider}:{binding.model}":
                    blocked.add(AvailableCommand.RUN_TD_QUALITY)
            commands = tuple(command for command in commands if command not in blocked)
        return WorkbenchSnapshot(
            **snapshot.model_dump(),
            execution_mode="managed" if managed else "legacy",
            available_commands=commands,
            jobs=tuple(runner.project_job_summary(snapshot, job) for job in jobs[-50:]),
            jobs_truncated=len(jobs) > 50,
            command_receipts=store.recent_commands(run_id),
            event_cursor=store.event_window(run_id)[1],
        )

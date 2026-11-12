"""Local Worker lease heartbeats use their own connection, never the API's objects."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread

from deliveryflow_contracts.execution import ModelJob

from deliveryflow_speccraft.execution_store import ExecutionStore


@contextmanager
def renew_while_running(
    database_path: Path,
    lease: ModelJob,
    *,
    interval_seconds: float = 10.0,
) -> Iterator[None]:
    if not 0 < interval_seconds <= 10:
        raise ValueError("invalid_heartbeat_interval")
    stop = Event()

    def heartbeat() -> None:
        try:
            store = ExecutionStore(database_path)
        except (sqlite3.Error, OSError):
            return
        try:
            while not stop.wait(interval_seconds):
                try:
                    store.renew_lease(lease)
                except (ValueError, sqlite3.Error, OSError):
                    return
        finally:
            store.close()

    thread = Thread(target=heartbeat, name="speccraft-lease", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()

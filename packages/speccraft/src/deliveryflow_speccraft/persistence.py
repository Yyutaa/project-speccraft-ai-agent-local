"""SQLite authority for the current Run projection and successful command IDs."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from threading import RLock
from types import TracebackType

from deliveryflow_contracts.runs import RunResponse


class CommandSet:
    def __init__(self, connection: sqlite3.Connection, run_id: str) -> None:
        self._connection = connection
        self._run_id = run_id

    def __contains__(self, command_id: object) -> bool:
        if not isinstance(command_id, str):
            return False
        return self._connection.execute(
            "SELECT 1 FROM successful_commands WHERE run_id = ? AND command_id = ?",
            (self._run_id, command_id),
        ).fetchone() is not None

    def add(self, command_id: str) -> None:
        self._connection.execute(
            "INSERT INTO successful_commands (run_id, command_id) VALUES (?, ?)",
            (self._run_id, command_id),
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, set) and set(self) == other

    def __iter__(self) -> Iterator[str]:
        rows = self._connection.execute(
            "SELECT command_id FROM successful_commands WHERE run_id = ?", (self._run_id,)
        )
        return (row[0] for row in rows)


class CommandSets:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __getitem__(self, run_id: str) -> CommandSet:
        return CommandSet(self._connection, run_id)

    def __setitem__(self, run_id: str, value: set[str]) -> None:
        if value:
            raise ValueError("new Run command IDs must be empty")

    def pop(self, run_id: str, default: None = None) -> None:
        self._connection.execute("DELETE FROM successful_commands WHERE run_id = ?", (run_id,))

    def __eq__(self, other: object) -> bool:
        if other != {}:
            return False
        row = self._connection.execute("SELECT 1 FROM successful_commands LIMIT 1").fetchone()
        return row is None


class RunStore:
    """One transaction spans a Runner command's Run and command-ID writes."""

    def __init__(self, database_path: Path | None = None) -> None:
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(database_path) if database_path is not None else ":memory:",
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise RuntimeError(f"unsupported Run Store schema version: {version}")
        self._connection.executescript(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS successful_commands ("
            "run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, "
            "command_id TEXT NOT NULL, PRIMARY KEY (run_id, command_id));"
            "PRAGMA user_version = 1;"
        )
        self.commands = CommandSets(self._connection)
        self._mutex = RLock()

    def __enter__(self) -> "RunStore":
        self._mutex.acquire()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except BaseException:
            self._mutex.release()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._connection.execute("COMMIT" if exc_type is None else "ROLLBACK")
        finally:
            self._mutex.release()

    def __getitem__(self, run_id: str) -> RunResponse:
        row = self._connection.execute(
            "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunResponse.model_validate_json(row[0])

    def __setitem__(self, run_id: str, run: RunResponse) -> None:
        run = RunResponse.model_validate(run.model_dump())
        self._connection.execute(
            "INSERT INTO runs (run_id, payload) VALUES (?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET payload = excluded.payload",
            (run_id, run.model_dump_json()),
        )

    def pop(self, run_id: str, default: None = None) -> None:
        self._connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def run_ids(self) -> tuple[str, ...]:
        with self._mutex:
            return tuple(row[0] for row in self._connection.execute("SELECT run_id FROM runs"))

    def __len__(self) -> int:
        with self._mutex:
            return self._connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def __eq__(self, other: object) -> bool:
        return other == {} and len(self) == 0

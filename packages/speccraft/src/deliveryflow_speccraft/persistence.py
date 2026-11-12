"""SQLite authority for the current Run projection and successful command IDs."""

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Literal
from uuid import uuid4

from deliveryflow_contracts.events import RunEvent
from deliveryflow_contracts.execution import (
    CommandReceipt,
    ModelBudgetPolicy,
    ModelBudgetUsage,
    ModelCallRecord,
    RunSnapshot,
)
from deliveryflow_contracts.model_tasks import TaskKind
from deliveryflow_contracts.runs import AvailableCommand, RunResponse


class ModelBudgetError(ValueError):
    """Stable accounting failures; no provider response or credential detail."""


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
        self._mutex = RLock()
        try:
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        except BaseException:
            self._connection.close()
            raise
        self.commands = CommandSets(self._connection)

    def close(self) -> None:
        """The owning host closes its connection after in-flight work stops."""
        with self._mutex:
            self._connection.close()

    def _migrate(self) -> None:
        with self:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4):
                raise RuntimeError(f"unsupported Run Store schema version: {version}")
            if version == 4:
                return
            if version < 2:
                self._migrate_runtime_tables()
            if version < 3:
                self._connection.execute(
                    "CREATE TABLE command_receipts ("
                    "run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, "
                    "command_id TEXT NOT NULL, payload TEXT NOT NULL, "
                    "PRIMARY KEY(run_id, command_id))"
                )
            self._migrate_execution_tables()
            self._connection.execute("PRAGMA user_version = 4")

    def _migrate_execution_tables(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS run_provider_bindings ("
            "run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE, "
            "payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS model_jobs ("
            "job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, command_id TEXT NOT NULL, "
            "task TEXT NOT NULL, baseline_hash TEXT NOT NULL, "
            "status TEXT NOT NULL "
            "CHECK(status IN ('queued','running','succeeded','failed','cancelled')), "
            "epoch INTEGER NOT NULL DEFAULT 0 CHECK(epoch >= 0), owner TEXT, lease_until REAL, "
            "created_at TEXT NOT NULL, error_code TEXT, "
            "FOREIGN KEY(run_id, command_id) REFERENCES command_receipts(run_id, command_id) "
            "ON DELETE CASCADE)"
        )
        self._connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS one_active_model_job ON model_jobs(run_id) "
            "WHERE status IN ('queued','running')"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS model_jobs_claim ON model_jobs(status, lease_until)"
        )

    def _migrate_runtime_tables(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS successful_commands ("
            "run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, "
            "command_id TEXT NOT NULL, PRIMARY KEY (run_id, command_id))"
        )
        self._connection.execute(
            "ALTER TABLE runs ADD COLUMN store_version INTEGER NOT NULL DEFAULT 0"
        )
        self._connection.execute(
            "CREATE TABLE run_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, "
            "run_version INTEGER NOT NULL, event_type TEXT NOT NULL, occurred_at TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE INDEX run_events_cursor ON run_events(run_id, id)"
        )
        self._connection.execute(
            "CREATE TABLE model_budgets ("
            "run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE, "
            "policy TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0 CHECK(calls >= 0), "
            "candidates INTEGER NOT NULL DEFAULT 0 CHECK(candidates >= 0))"
        )
        self._connection.execute(
            "CREATE TABLE model_calls (id TEXT PRIMARY KEY, "
            "run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, "
            "payload TEXT NOT NULL)"
        )
        self._connection.execute(
            "CREATE INDEX model_calls_run ON model_calls(run_id)"
        )
        self._connection.execute(
            "CREATE TABLE model_candidates (id TEXT PRIMARY KEY, "
            "run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, "
            "command_id TEXT NOT NULL, issue_id TEXT NOT NULL, candidate_hash TEXT NOT NULL)"
        )

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
            if exc_type is None:
                try:
                    self._connection.execute("COMMIT")
                except BaseException:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
            else:
                self._connection.execute("ROLLBACK")
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
        if run.run_id != run_id:
            raise ValueError("run_identity_conflict")
        with self._mutex:
            if not self._connection.in_transaction:
                with self:
                    self._write(run_id, run)
            else:
                self._write(run_id, run)

    def _write(self, run_id: str, run: RunResponse) -> None:
        self._connection.execute(
            "INSERT INTO runs (run_id, payload, store_version) VALUES (?, ?, 0) "
            "ON CONFLICT(run_id) DO UPDATE SET payload = excluded.payload",
            (run_id, run.model_dump_json()),
        )
        self._event(run_id, "run.changed")

    def _event(self, run_id: str, event_type: str) -> None:
        self._connection.execute(
            "UPDATE runs SET store_version = store_version + 1 WHERE run_id = ?", (run_id,)
        )
        self._connection.execute(
            "INSERT INTO run_events(run_id, run_version, event_type, occurred_at) "
            "SELECT run_id, store_version, ?, ? FROM runs WHERE run_id = ?",
            (event_type, datetime.now(UTC).isoformat(), run_id),
        )

    def snapshot(self, run_id: str) -> RunSnapshot:
        with self._mutex:
            row = self._connection.execute(
                "SELECT r.payload, r.store_version, b.policy, b.calls, b.candidates "
                "FROM runs r LEFT JOIN model_budgets b ON b.run_id = r.run_id "
                "WHERE r.run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            budget = ModelBudgetUsage(
                run_id=run_id, policy=ModelBudgetPolicy.model_validate_json(row[2]),
                model_calls=row[3], candidates=row[4],
            ) if row[2] is not None else None
            return RunSnapshot(
                run=RunResponse.model_validate_json(row[0]),
                run_version=row[1], model_budget=budget,
            )

    def compare_and_set(
        self, run_id: str, expected_version: int, run: RunResponse
    ) -> RunSnapshot:
        if isinstance(expected_version, bool) or expected_version < 0:
            raise ValueError("invalid_run_version")
        run = RunResponse.model_validate(run.model_dump())
        if run.run_id != run_id:
            raise ValueError("run_identity_conflict")
        with self:
            result = self._connection.execute(
                "UPDATE runs SET payload = ? WHERE run_id = ? AND store_version = ?",
                (run.model_dump_json(), run_id, expected_version),
            )
            if result.rowcount != 1:
                self.snapshot(run_id)  # Distinguish an unknown Run from a stale version.
                raise ValueError("run_version_conflict")
            self._event(run_id, "run.changed")
            return self.snapshot(run_id)

    def events_after(self, run_id: str, cursor: int, limit: int = 200) -> tuple[RunEvent, ...]:
        if isinstance(cursor, bool) or cursor < 0 or not 1 <= limit <= 200:
            raise ValueError("invalid_event_cursor")
        with self._mutex:
            rows = self._connection.execute(
                "SELECT id, run_id, run_version, event_type, occurred_at FROM run_events "
                "WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?", (run_id, cursor, limit),
            ).fetchall()
        return tuple(RunEvent(
            event_id=r[0], run_id=r[1], run_version=r[2], event_type=r[3], occurred_at=r[4],
        ) for r in rows)

    def initialize_model_budget(self, run_id: str, policy: ModelBudgetPolicy) -> None:
        """Called inside the same Store transaction that creates the Run."""
        if not self._connection.in_transaction:
            raise RuntimeError("model budget initialization requires a transaction")
        policy = ModelBudgetPolicy.model_validate(policy.model_dump())
        existing = self._connection.execute(
            "SELECT policy FROM model_budgets WHERE run_id = ?", (run_id,)
        ).fetchone()
        if existing:
            if ModelBudgetPolicy.model_validate_json(existing[0]) != policy:
                raise ModelBudgetError("model_budget_policy_conflict")
            return
        self._connection.execute(
            "INSERT INTO model_budgets(run_id, policy) VALUES (?, ?)",
            (run_id, policy.model_dump_json()),
        )

    def model_budget(self, run_id: str) -> ModelBudgetUsage:
        with self._mutex:
            row = self._connection.execute(
                "SELECT policy, calls, candidates FROM model_budgets WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ModelBudgetError("model_budget_uninitialized")
        return ModelBudgetUsage(
            run_id=run_id, policy=ModelBudgetPolicy.model_validate_json(row[0]),
            model_calls=row[1], candidates=row[2],
        )

    def reserve_model_call(
        self, run_id: str, command_id: str, input_binding: str, task_kind: TaskKind
    ) -> ModelCallRecord:
        record = ModelCallRecord(
            call_id=str(uuid4()), run_id=run_id, command_id=command_id,
            input_binding=input_binding, task_kind=task_kind,
        )
        with self._write_scope():
            usage = self.model_budget(run_id)
            if usage.model_calls >= usage.policy.max_model_calls:
                raise ModelBudgetError("run_model_budget_exhausted")
            self._connection.execute(
                "UPDATE model_budgets SET calls = calls + 1 WHERE run_id = ?", (run_id,)
            )
            self._connection.execute(
                "INSERT INTO model_calls(id, run_id, payload) VALUES (?, ?, ?)",
                (record.call_id, run_id, record.model_dump_json()),
            )
            self._event(run_id, "model.call_reserved")
        return record

    def finish_model_call(
        self, call_id: str, status: Literal["succeeded", "failed", "interrupted"]
    ) -> None:
        with self._write_scope():
            row = self._connection.execute(
                "SELECT payload FROM model_calls WHERE id = ?", (call_id,)
            ).fetchone()
            if row is None:
                raise KeyError(call_id)
            record = ModelCallRecord.model_validate_json(row[0])
            if record.status == status:
                return
            if record.status != "reserved":
                raise ValueError("model_call_status_conflict")
            updated = ModelCallRecord.model_validate(record.model_dump() | {"status": status})
            self._connection.execute(
                "UPDATE model_calls SET payload = ? WHERE id = ?",
                (updated.model_dump_json(), call_id),
            )
            self._event(record.run_id, "model.call_finished")

    def model_calls(self, run_id: str) -> tuple[ModelCallRecord, ...]:
        with self._mutex:
            rows = self._connection.execute(
                "SELECT payload FROM model_calls WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        return tuple(ModelCallRecord.model_validate_json(row[0]) for row in rows)

    def reserve_candidate(
        self, run_id: str, command_id: str, issue_id: str, candidate_hash: str
    ) -> None:
        if (
            not command_id.strip() or not issue_id.strip()
            or not re.fullmatch(r"[0-9a-f]{64}", candidate_hash)
        ):
            raise ValueError("invalid_candidate_reservation")
        with self._mutex:
            if self._connection.in_transaction:
                self._reserve_candidate(run_id, command_id, issue_id, candidate_hash)
            else:
                with self:
                    self._reserve_candidate(run_id, command_id, issue_id, candidate_hash)

    def _reserve_candidate(
        self, run_id: str, command_id: str, issue_id: str, candidate_hash: str
    ) -> None:
        usage = self.model_budget(run_id)
        if usage.candidates >= usage.policy.max_candidates:
            raise ModelBudgetError("run_candidate_budget_exhausted")
        self._connection.execute(
            "UPDATE model_budgets SET candidates = candidates + 1 WHERE run_id = ?", (run_id,)
        )
        self._connection.execute(
            "INSERT INTO model_candidates VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), run_id, command_id, issue_id, candidate_hash),
        )
        self._event(run_id, "model.candidate_reserved")

    @contextmanager
    def _write_scope(self) -> Iterator[None]:
        """Join a caller's short transaction, or establish an atomic standalone one."""
        with self._mutex:
            if self._connection.in_transaction:
                yield
            else:
                with self:
                    yield

    def accept_command(
        self, run_id: str, command_id: str, kind: AvailableCommand, payload: dict[str, object],
        *, expected_version: int,
    ) -> CommandReceipt:
        if isinstance(expected_version, bool) or expected_version < 0:
            raise ValueError("invalid_run_version")
        canonical = json.dumps(
            {"kind": kind, "payload": payload, "expected_version": expected_version},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        if len(canonical) > 256 * 1024:
            raise ValueError("command_payload_too_large")
        receipt = CommandReceipt(
            run_id=run_id, command_id=command_id, kind=kind,
            request_hash=sha256(canonical).hexdigest(),
        )
        with self._write_scope():
            row = self._connection.execute(
                "SELECT payload FROM command_receipts WHERE run_id = ? AND command_id = ?",
                (run_id, command_id),
            ).fetchone()
            if row:
                prior = CommandReceipt.model_validate_json(row[0])
                raise ValueError(
                    "duplicate_command" if prior.request_hash == receipt.request_hash
                    else "command_payload_conflict"
                )
            if command_id in self.commands[run_id]:
                raise ValueError("duplicate_command")
            if self.snapshot(run_id).run_version != expected_version:
                raise ValueError("run_version_conflict")
            self._connection.execute(
                "INSERT INTO command_receipts(run_id, command_id, payload) VALUES (?, ?, ?)",
                (run_id, command_id, receipt.model_dump_json()),
            )
            self._event(run_id, "command.accepted")
        return receipt

    def get_command(self, run_id: str, command_id: str) -> CommandReceipt:
        with self._mutex:
            row = self._connection.execute(
                "SELECT payload FROM command_receipts WHERE run_id = ? AND command_id = ?",
                (run_id, command_id),
            ).fetchone()
        if row is None:
            raise KeyError(command_id)
        return CommandReceipt.model_validate_json(row[0])

    def finish_command(
        self, run_id: str, command_id: str,
        status: Literal["succeeded", "failed", "cancelled"], *, error_code: str | None = None,
    ) -> CommandReceipt:
        with self._write_scope():
            prior = self.get_command(run_id, command_id)
            if prior.status != "accepted":
                raise ValueError("command_outcome_conflict")
            receipt = CommandReceipt.model_validate(prior.model_dump() | {
                "status": status, "error_code": error_code, "finished_at": datetime.now(UTC),
            })
            self._connection.execute(
                "UPDATE command_receipts SET payload = ? WHERE run_id = ? AND command_id = ?",
                (receipt.model_dump_json(), run_id, command_id),
            )
            self._event(run_id, "command.finished")
        return receipt

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

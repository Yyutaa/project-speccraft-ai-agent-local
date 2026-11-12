"""Durable versions, notification facts and resource reservations."""

import importlib
import sqlite3

import pytest
from deliveryflow_contracts.runs import CreateRunRequest
from deliveryflow_speccraft.composition import build_runner
from deliveryflow_speccraft.persistence import RunStore
from test_composition import ROOT


def created(tmp_path, budget=None):
    path = tmp_path / "runs.sqlite3"
    runner = build_runner(ROOT, database_path=path, model_budget_policy=budget)
    run = runner.create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="不要出现在事件中的原始需求。",
        )
    )
    return path, runner, run


def policy(**values):
    contracts = importlib.import_module("deliveryflow_contracts.execution")
    return contracts.ModelBudgetPolicy(**values)


def test_snapshot_version_and_event_are_atomic_and_survive_restart(tmp_path):
    path, runner, run = created(tmp_path)
    store = RunStore(path)
    snapshot = store.snapshot(run.run_id)
    assert snapshot.run == run
    assert snapshot.run_version == 1
    events = store.events_after(run.run_id, 0)
    assert len(events) == 1
    assert events[0].run_version == 1
    assert run.requirement not in events[0].model_dump_json()
    assert RunStore(path).events_after(run.run_id, 0) == events
    assert runner.get_run(run.run_id) == run


def test_two_connections_cannot_overwrite_a_newer_run_version(tmp_path):
    path, _, run = created(tmp_path)
    first, second = RunStore(path), RunStore(path)
    original = first.snapshot(run.run_id)
    winner = first.compare_and_set(run.run_id, original.run_version, run)
    assert winner.run_version == original.run_version + 1
    with pytest.raises(ValueError, match="run_version_conflict"):
        second.compare_and_set(run.run_id, original.run_version, run)
    assert second.snapshot(run.run_id) == winner
    assert len(second.events_after(run.run_id, 0)) == 2


def test_event_failure_rolls_back_run_write_and_version(tmp_path):
    path, _, run = created(tmp_path)
    store = RunStore(path)
    original = store.snapshot(run.run_id)
    store._connection.execute(
        "CREATE TRIGGER fail_event BEFORE INSERT ON run_events "
        "BEGIN SELECT RAISE(ABORT, 'event write failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="event write failed"):
        store.compare_and_set(run.run_id, original.run_version, run)
    assert store.snapshot(run.run_id) == original
    assert len(store.events_after(run.run_id, 0)) == 1


def test_events_are_run_scoped_ordered_and_bounded(tmp_path):
    path, _, run = created(tmp_path)
    other = build_runner(ROOT, database_path=path).create_run(
        CreateRunRequest(
            governance_contract_version=2,
            requirement="其他运行。",
        )
    )
    store = RunStore(path)
    store.compare_and_set(run.run_id, 1, run)
    first = store.events_after(run.run_id, 0, limit=1)
    later = store.events_after(run.run_id, first[0].event_id)
    assert len(later) == 1 and later[0].event_id > first[0].event_id
    assert all(e.run_id == run.run_id for e in first + later)
    assert all(e.run_id == other.run_id for e in store.events_after(other.run_id, 0))
    with pytest.raises(ValueError):
        store.events_after(run.run_id, -1)


def test_budget_is_server_frozen_and_reservations_survive_failures_and_restart(
    tmp_path,
):
    path, _, run = created(tmp_path, budget=policy(max_model_calls=2, max_candidates=1))
    store = RunStore(path)
    # Server-side initialization is part of the Run creation transaction.
    with store:
        store.initialize_model_budget(
            run.run_id, policy(max_model_calls=2, max_candidates=1)
        )
    call = store.reserve_model_call(run.run_id, "command-1", "a" * 64, "td_quality")
    store.finish_model_call(call.call_id, "failed")
    second = RunStore(path)
    second.reserve_model_call(run.run_id, "command-2", "b" * 64, "td_quality")
    before = second.model_budget(run.run_id)
    assert before.model_calls == 2
    assert second.model_calls(run.run_id)[1].status == "reserved"
    with pytest.raises(ValueError, match="run_model_budget_exhausted"):
        second.reserve_model_call(run.run_id, "new-command", "c" * 64, "prd_author")
    assert second.model_budget(run.run_id) == before
    with second, pytest.raises(ValueError, match="model_budget_policy_conflict"):
        second.initialize_model_budget(run.run_id, policy(max_model_calls=3))


def test_candidate_budget_is_shared_across_commands_and_issues(tmp_path):
    path, _, run = created(tmp_path, budget=policy(max_candidates=1))
    store = RunStore(path)
    with store:
        store.initialize_model_budget(run.run_id, policy(max_candidates=1))
    store.reserve_candidate(run.run_id, "patch-1", "issue-1", "a" * 64)
    before = store.model_budget(run.run_id)
    with pytest.raises(ValueError, match="run_candidate_budget_exhausted"):
        RunStore(path).reserve_candidate(run.run_id, "patch-2", "issue-2", "b" * 64)
    assert store.model_budget(run.run_id) == before
    assert before.candidates == 1


def test_call_reservation_failure_does_not_charge_or_emit_event(tmp_path):
    path, _, run = created(tmp_path)
    store = RunStore(path)
    with store:
        store.initialize_model_budget(run.run_id, policy())
    store._connection.execute(
        "CREATE TRIGGER fail_call BEFORE INSERT ON model_calls "
        "BEGIN SELECT RAISE(ABORT, 'call write failed'); END"
    )
    events = store.events_after(run.run_id, 0)
    with pytest.raises(sqlite3.IntegrityError, match="call write failed"):
        store.reserve_model_call(run.run_id, "command", "a" * 64, "td_quality")
    assert store.model_budget(run.run_id).model_calls == 0
    assert store.events_after(run.run_id, 0) == events


def test_legacy_run_migration_does_not_fabricate_a_budget_or_history(tmp_path):
    _, _, run = created(tmp_path)
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
        "CREATE TABLE successful_commands (run_id TEXT, command_id TEXT, "
        "PRIMARY KEY(run_id, command_id)); PRAGMA user_version=1;"
    )
    connection.execute(
        "INSERT INTO runs VALUES (?, ?)", (run.run_id, run.model_dump_json())
    )
    connection.commit()
    connection.close()
    store = RunStore(path)
    assert store[run.run_id] == run
    assert store.snapshot(run.run_id).run_version == 0
    assert store.events_after(run.run_id, 0) == ()
    with pytest.raises(ValueError, match="model_budget_uninitialized"):
        store.reserve_model_call(run.run_id, "command", "a" * 64, "td_quality")


def test_migration_failure_rolls_back_ddl_and_schema_version(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
        "CREATE TABLE successful_commands (run_id TEXT, command_id TEXT);"
        "PRAGMA user_version=1;"
    )
    connection.close()
    connect = sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if "CREATE TABLE" in sql and "model_calls" in sql:
                raise sqlite3.OperationalError("migration interrupted")
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *a, **kw: connect(
            *a,
            **kw,
            factory=FailingConnection,
        ),
    )
    with pytest.raises(sqlite3.OperationalError, match="migration interrupted"):
        RunStore(path)
    check = connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == 1
    assert [r[1] for r in check.execute("PRAGMA table_info(runs)")] == [
        "run_id",
        "payload",
    ]
    check.close()


def test_competing_connections_cannot_overdraw_the_last_call(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path, _, run = created(tmp_path, budget=policy(max_model_calls=1))
    stores = [RunStore(path), RunStore(path)]
    barrier = Barrier(2)

    def reserve(index):
        barrier.wait(timeout=5)
        try:
            stores[index].reserve_model_call(
                run.run_id, f"command-{index}", "a" * 64, "td_quality"
            )
            return "reserved"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, range(2)))
    assert sorted(results) == ["reserved", "run_model_budget_exhausted"]
    assert stores[0].model_budget(run.run_id).model_calls == 1
    assert len(stores[0].model_calls(run.run_id)) == 1
    snapshot = stores[0].snapshot(run.run_id)
    assert snapshot.model_budget.model_calls == 1
    assert snapshot.run_version == 2


def test_failed_commit_rolls_back_and_connection_remains_usable(tmp_path, monkeypatch):
    path, _, run = created(tmp_path)
    connect = sqlite3.connect

    class FailingCommit(sqlite3.Connection):
        fail_commit = False

        def execute(self, sql, *args, **kwargs):
            if sql == "COMMIT" and self.fail_commit:
                self.fail_commit = False
                raise sqlite3.OperationalError("commit interrupted")
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *a, **kw: connect(
            *a,
            **kw,
            factory=FailingCommit,
        ),
    )
    store = RunStore(path)
    baseline = store.snapshot(run.run_id)
    store._connection.fail_commit = True
    with pytest.raises(sqlite3.OperationalError, match="commit interrupted"):
        store.compare_and_set(run.run_id, baseline.run_version, run)
    assert not store._connection.in_transaction
    assert store.snapshot(run.run_id) == baseline
    assert store.compare_and_set(run.run_id, baseline.run_version, run).run_version == 2

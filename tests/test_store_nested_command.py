"""Shared Runner commands may join a managed receipt transaction safely."""

import pytest
from deliveryflow_speccraft.execution_store import ExecutionStore


def test_nested_command_rollback_retains_outer_transaction(tmp_path):
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    with store:
        store._connection.execute("CREATE TABLE nested_test(value TEXT)")
        store._connection.execute("INSERT INTO nested_test VALUES ('outer')")
        with pytest.raises(RuntimeError, match="inner"), store:
            store._connection.execute("INSERT INTO nested_test VALUES ('inner')")
            raise RuntimeError("inner")
        assert store._connection.execute(
            "SELECT value FROM nested_test"
        ).fetchall() == [("outer",)]
    assert store._connection.execute("SELECT value FROM nested_test").fetchall() == [
        ("outer",)
    ]


def test_nested_success_cannot_escape_outer_failure(tmp_path):
    store = ExecutionStore(tmp_path / "runs.sqlite3")
    store._connection.execute("CREATE TABLE nested_test(value TEXT)")
    with pytest.raises(RuntimeError, match="outer"), store:
        with store:
            store._connection.execute("INSERT INTO nested_test VALUES ('inner')")
        raise RuntimeError("outer")
    assert store._connection.execute("SELECT * FROM nested_test").fetchall() == []

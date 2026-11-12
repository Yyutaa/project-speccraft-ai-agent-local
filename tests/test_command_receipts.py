"""Accepted commands and their outcomes are durable, distinct from approvals."""

import sqlite3

import pytest
from deliveryflow_contracts.runs import AvailableCommand
from deliveryflow_speccraft.persistence import RunStore
from test_runtime_store import created


def test_receipt_deduplicates_payload_and_survives_restart_without_advancing_run(
    tmp_path,
):
    path, _, run = created(tmp_path)
    store = RunStore(path)
    payload = {"governance_contract_version": 2, "actor_claim": "reviewer"}
    receipt = store.accept_command(
        run.run_id,
        "command-1",
        AvailableCommand.RECORD_TD_REVIEW,
        payload,
        expected_version=1,
    )
    assert receipt.status == "accepted"
    assert store[run.run_id] == run  # Acceptance cannot invent a domain transition.
    assert RunStore(path).get_command(run.run_id, "command-1") == receipt
    # Equivalent object key ordering is a duplicate, not a new command.
    with pytest.raises(ValueError, match="duplicate_command"):
        store.accept_command(
            run.run_id,
            "command-1",
            AvailableCommand.RECORD_TD_REVIEW,
            dict(reversed(list(payload.items()))),
            expected_version=1,
        )
    with pytest.raises(ValueError, match="command_payload_conflict"):
        store.accept_command(
            run.run_id,
            "command-1",
            AvailableCommand.RECORD_TD_REVIEW,
            {**payload, "actor_claim": "someone-else"},
            expected_version=1,
        )
    assert len(store.events_after(run.run_id, 0)) == 2


def test_stale_acceptance_leaves_no_receipt_or_event(tmp_path):
    path, _, run = created(tmp_path)
    store = RunStore(path)
    with pytest.raises(ValueError, match="run_version_conflict"):
        store.accept_command(
            run.run_id,
            "stale",
            AvailableCommand.APPROVE_PRD,
            {},
            expected_version=0,
        )
    with pytest.raises(KeyError):
        store.get_command(run.run_id, "stale")
    assert store.snapshot(run.run_id).run_version == 1


def test_outcome_is_atomic_with_event_and_terminal_receipt_cannot_be_overwritten(
    tmp_path,
):
    path, _, run = created(tmp_path)
    store = RunStore(path)
    store.accept_command(
        run.run_id,
        "command-1",
        AvailableCommand.RUN_TD_QUALITY,
        {},
        expected_version=1,
    )
    store._connection.execute(
        "CREATE TRIGGER fail_outcome BEFORE INSERT ON run_events "
        "WHEN NEW.event_type='command.finished' "
        "BEGIN SELECT RAISE(ABORT, 'outcome event failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="outcome event failed"):
        store.finish_command(
            run.run_id, "command-1", "failed", error_code="provider_timeout"
        )
    assert store.get_command(run.run_id, "command-1").status == "accepted"
    store._connection.execute("DROP TRIGGER fail_outcome")
    done = store.finish_command(
        run.run_id, "command-1", "failed", error_code="provider_timeout"
    )
    assert done.status == "failed"
    assert store[run.run_id] == run
    with pytest.raises(ValueError, match="command_outcome_conflict"):
        store.finish_command(run.run_id, "command-1", "succeeded")
    assert RunStore(path).get_command(run.run_id, "command-1") == done


def test_v2_database_upgrades_without_inventing_receipts(tmp_path):
    path, _, run = created(tmp_path)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE IF EXISTS command_receipts")
    connection.execute("PRAGMA user_version = 2")
    connection.close()
    store = RunStore(path)
    assert store[run.run_id] == run
    with pytest.raises(KeyError):
        store.get_command(run.run_id, "not-recorded")
    assert store.model_budget(run.run_id).model_calls == 0

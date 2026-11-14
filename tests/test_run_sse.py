"""SSE transports versioned invalidation hints, never domain bodies or approvals."""

import asyncio

from test_managed_prd import ready, submission

from apps.api.run_events import open_stream, run_event_stream


def take(runner, start, count):
    async def collect():
        stream = run_event_stream(
            runner, start, poll_seconds=0.001, heartbeat_seconds=0.001
        )
        try:
            return [await asyncio.wait_for(anext(stream), 1) for _ in range(count)]
        finally:
            await stream.aclose()

    return asyncio.run(collect())


def test_first_connection_only_signals_current_cursor_and_idle_heartbeat(tmp_path):
    runner, _, run = ready(tmp_path)
    frames = take(runner, open_stream(runner, run.run_id, 0), 2)
    assert frames[0].event == "ready"
    assert int(frames[0].id) > 0
    assert frames[0].data["run_id"] == run.run_id
    assert "content" not in frames[0].data and "ledger" not in frames[0].data
    assert frames[1].comment == "keep-alive"
    assert frames[1].event == "heartbeat"
    assert frames[1].id is None
    assert frames[1].data["event_type"] == "stream.heartbeat"


def test_valid_cursor_replays_only_same_run_events_in_order(tmp_path):
    runner, service, run = ready(tmp_path)
    cursor = runner._runs.event_window(run.run_id)[1]
    service.submit_clarification(run.run_id, submission(runner, run))
    expected = runner.get_events(run.run_id, cursor)
    frames = take(runner, open_stream(runner, run.run_id, cursor), len(expected) + 1)
    assert frames[0].event == "ready" and frames[0].id == str(cursor)
    assert [int(f.id) for f in frames[1:]] == [e.event_id for e in expected]
    assert all(f.event == "update" for f in frames[1:])
    assert all(f.data["run_id"] == run.run_id for f in frames)


def test_foreign_future_and_unretained_cursor_request_rest_recalibration(tmp_path):
    runner, _, run = ready(tmp_path)
    latest = runner._runs.event_window(run.run_id)[1]
    for cursor in (latest + 100000,):
        frame = take(runner, open_stream(runner, run.run_id, cursor), 1)[0]
        assert frame.event == "reset" and frame.id == str(latest)
    runner._runs._connection.execute(
        "DELETE FROM run_events WHERE run_id=? AND id=?", (run.run_id, latest)
    )
    frame = take(runner, open_stream(runner, run.run_id, latest), 1)[0]
    assert frame.event == "reset"


def test_stream_does_not_hold_transaction_while_waiting_or_after_close(tmp_path):
    runner, _, run = ready(tmp_path)
    take(runner, open_stream(runner, run.run_id, 0), 2)
    assert not runner._runs._connection.in_transaction


def test_last_event_id_validation_and_unknown_run_happen_before_stream_headers(
    tmp_path, monkeypatch
):
    from test_managed_prd_api import client_for

    runner, _, run = ready(tmp_path)
    client = client_for(runner, monkeypatch)
    assert client.get("/api/runs/missing/events/stream").status_code == 404
    assert (
        client.get(
            f"/api/runs/{run.run_id}/events/stream", headers={"Last-Event-ID": "-1"}
        ).status_code
        == 422
    )
    assert (
        client.get(f"/api/runs/{run.run_id}/events/stream?after=-1").status_code == 422
    )


def test_foreign_cursor_does_not_replay_another_runs_history(tmp_path):
    from test_managed_clarification import request

    runner, service, run = ready(tmp_path)
    other = service.create_run(request())
    foreign = runner._runs.event_window(other.run_id)[1]
    frame = take(runner, open_stream(runner, run.run_id, foreign), 1)[0]
    assert frame.event == "reset"
    assert frame.data["run_id"] == run.run_id


def completed():
    from governance_helpers import td_review_request
    from test_td_review import approval, awaiting_td
    from test_td_runner import runner as subject

    runner = subject()
    run = awaiting_td(runner)
    run = runner.record_td_review(run.run_id, td_review_request(run))
    return runner, runner.approve_td(run.run_id, approval(run))


def test_terminal_rest_stream_has_correct_headers_and_no_document_body(monkeypatch):
    from test_managed_prd_api import client_for

    runner, run = completed()
    client = client_for(runner, monkeypatch)
    response = client.get(f"/api/runs/{run.run_id}/events/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: ready" in response.text and "event: terminal" in response.text
    assert run.prd_draft.content not in response.text
    assert "invalidates" in response.text


def test_last_event_id_overrides_query_and_replays_bounded_pages(monkeypatch):
    from test_managed_prd_api import client_for

    runner, run = completed()
    first = runner._runs.event_window(run.run_id)[0]
    client = client_for(runner, monkeypatch)
    response = client.get(
        f"/api/runs/{run.run_id}/events/stream?after=999999999",
        headers={"Last-Event-ID": str(first)},
    )
    assert "event: reset" not in response.text
    assert "event: update" in response.text and "event: terminal" in response.text


def test_historical_run_with_zero_events_still_notifies_first_new_change(tmp_path):
    runner,_,run=ready(tmp_path)
    runner._runs._connection.execute('DELETE FROM run_events WHERE run_id=?',(run.run_id,))
    async def exercise():
        stream=run_event_stream(runner,open_stream(runner,run.run_id,0),poll_seconds=0.001)
        try:
            initial=await anext(stream)
            assert initial.event=='ready' and initial.id=='0'
            runner._runs[run.run_id]=run
            updated=await asyncio.wait_for(anext(stream),0.5)
            assert updated.event=='update'
        finally:
            await stream.aclose()
    asyncio.run(exercise())

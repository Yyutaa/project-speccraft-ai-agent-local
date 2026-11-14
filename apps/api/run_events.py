"""Local SSE adapter over the transactional event log, with no domain write authority."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import monotonic

from deliveryflow_contracts.events import RunEvent, RunUpdateHint
from deliveryflow_speccraft.runner import RunRunner
from fastapi.sse import ServerSentEvent


@dataclass(frozen=True)
class StreamStart:
    run_id: str
    cursor: int


@dataclass(frozen=True)
class EventPage:
    version: int
    latest: int
    cursor_present: bool
    terminal: bool
    events: tuple[RunEvent, ...]


def open_stream(runner: RunRunner, run_id: str, cursor: int) -> StreamStart:
    if isinstance(cursor, bool) or not 0 <= cursor <= 2**63 - 1:
        raise ValueError("invalid_event_cursor")
    runner.get_snapshot(run_id)  # Fail with 404 before response headers are sent.
    return StreamStart(run_id, cursor)


def event_page(runner: RunRunner, run_id: str, cursor: int) -> EventPage:
    store = runner._runs
    with store._read_scope():
        snapshot = runner.get_snapshot(run_id)
        _, latest, present = store.event_window(run_id, cursor)
        return EventPage(
            version=snapshot.run_version,
            latest=latest,
            cursor_present=present,
            terminal=snapshot.run.status == "completed",
            events=store.events_after(run_id, cursor) if present else (),
        )


async def run_event_stream(
    runner: RunRunner,
    start: StreamStart,
    *,
    poll_seconds: float = 0.5,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[ServerSentEvent]:
    """At-least-once hints. Reconnecting consumers re-read REST and tolerate repeats."""
    cursor = start.cursor
    first = True
    last_output = monotonic()

    def hint(
        kind: str, identifier: int, version: int, event_type: str
    ) -> ServerSentEvent:
        return ServerSentEvent(
            event=kind,
            id=str(identifier),
            retry=2000,
            data=RunUpdateHint(
                event_id=identifier,
                run_id=start.run_id,
                run_version=version,
                event_type=event_type,
            ).model_dump(mode="json"),
        )

    while True:
        # A slow SQLite reader runs in a thread; never block the ASGI event loop
        # or retain a database transaction during the following yield/sleep.
        page = await asyncio.to_thread(event_page, runner, start.run_id, cursor)
        events = page.events
        if not page.cursor_present:
            cursor = page.latest
            yield hint("reset", cursor, page.version, "cursor.reset")
            last_output = monotonic()
        elif first:
            if cursor == 0:
                cursor = page.latest  # Initial business data comes from REST.
                events = ()
            yield hint("ready", cursor, page.version, "stream.ready")
            last_output = monotonic()
        for event in events:
            cursor = event.event_id
            yield hint("update", cursor, event.run_version, event.event_type)
            last_output = monotonic()
        first = False
        if page.terminal and cursor >= page.latest:
            yield hint("terminal", cursor, page.version, "stream.terminal")
            return
        if monotonic() - last_output >= heartbeat_seconds:
            # Comments keep proxies alive; a named heartbeat also lets clients detect
            # a half-open downstream connection whose proxy never reports an error.
            yield ServerSentEvent(
                comment="keep-alive",
                event="heartbeat",
                data=RunUpdateHint(
                    event_id=cursor,
                    run_id=start.run_id,
                    run_version=page.version,
                    event_type="stream.heartbeat",
                ).model_dump(mode="json"),
            )
            last_output = monotonic()
        if not events or cursor >= page.latest:
            await asyncio.sleep(poll_seconds)

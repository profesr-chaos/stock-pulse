"""Live-update push channel.

One message type: {"type": "changed"}, sent whenever anything was committed to
the database — the scheduler process writing prices or news, a POST from
another tab editing the watchlist. Clients then re-fetch over REST; the socket
only ever says "ask again", it never carries data. That is what makes it
impossible for this channel to serve stale or partial state.

CORS does not apply to WebSockets, so the handshake re-checks Origin against
the same allow-list the REST middleware uses. Clients that send no Origin
(curl, scripts) are as trusted here as they are on any REST endpoint.

The change signal is Postgres LISTEN/NOTIFY, fired by the statement-level
triggers in db/connection.py. Under SQLite this polled `PRAGMA data_version`
every five seconds, because that was the only cross-process change signal
available without standing up a bus. Postgres has a real one, so an update is
now pushed rather than noticed up to five seconds late.

Statement-level triggers plus the coalescing window below are what keep a
refresh that stores 500 articles from becoming 500 socket messages.
"""
from __future__ import annotations

import asyncio
import threading

import psycopg
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

import settings

router = APIRouter(tags=["System"])

CHANNEL = "stocky_changed"

# The listener is a sync connection on a thread rather than psycopg's async
# API, because psycopg refuses to run async on Windows' ProactorEventLoop —
# which is exactly what uvicorn uses here by default. Threading it sidesteps
# the event-loop policy entirely instead of forcing a global change on the
# whole app to suit one endpoint.
#
# ponytail: one thread per open socket. Fine for a single-user tool with a
# handful of tabs; share one listener across sockets if that ever stops being
# true.
_STOP_CHECK_SECONDS = 1.0

# A refresh commits many statements across several minutes of scraping. The
# client gains nothing from a second message in the same breath — the first one
# already invalidated every query — so a burst is flattened to one message per
# window. Leading edge, so an isolated change still arrives immediately and
# only a storm is throttled.
COALESCE_SECONDS = 2.0


@router.websocket("/ws")
async def live_updates(ws: WebSocket) -> None:
    origin = ws.headers.get("origin")
    if origin is not None and origin not in settings.CORS_ORIGINS:
        await ws.close(code=1008)  # policy violation
        return

    changed = asyncio.Event()
    stop, subscribed = threading.Event(), threading.Event()
    listener = threading.Thread(
        target=_listen,
        args=(asyncio.get_running_loop(), changed, stop, subscribed),
        name="ws-listen",
        daemon=True,
    )
    listener.start()

    # Subscribed *before* the handshake completes, not after. The other order
    # leaves a gap in which the client believes it is connected while the
    # server is not yet listening, and anything committed inside that gap is
    # missed with no later message to correct it.
    await asyncio.to_thread(subscribed.wait, 10.0)
    await ws.accept()

    try:
        while True:
            await changed.wait()
            changed.clear()
            await ws.send_json({"type": "changed"})
            await asyncio.sleep(COALESCE_SECONDS)
    # ponytail: a silently-vanished client is only noticed at the next send or
    # uvicorn's ws ping (20s default); add a reader task if that ever matters.
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        stop.set()


def _listen(loop, changed: asyncio.Event,
            stop: threading.Event, subscribed: threading.Event) -> None:
    """Wake the socket on every NOTIFY, on its own connection.

    Its own connection because LISTEN is session-scoped and this holds it for
    the life of the socket — borrowing from the request pool would take one out
    of circulation for as long as a browser tab stays open.
    """
    conn = psycopg.connect(settings.DB_DSN, autocommit=True)
    try:
        conn.execute(f"LISTEN {CHANNEL}")
        subscribed.set()
        while not stop.is_set():
            # stop_after returns the moment a notification lands, so the push
            # stays immediate; the timeout only bounds how long an *idle* wait
            # runs before rechecking whether the socket has gone away.
            for _ in conn.notifies(timeout=_STOP_CHECK_SECONDS, stop_after=1):
                loop.call_soon_threadsafe(changed.set)
    finally:
        subscribed.set()  # never leave the handshake blocked on a failed connect
        conn.close()

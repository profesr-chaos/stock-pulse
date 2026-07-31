"""Live-update push channel.

One message type: {"type": "changed"}, sent whenever anything was committed to
the database — the scheduler process writing prices or news, a POST from
another tab editing the watchlist. Clients then re-fetch over REST; the socket
only ever says "ask again", it never carries data.

CORS does not apply to WebSockets, so the handshake re-checks Origin against
the same allow-list the REST middleware uses. Clients that send no Origin
(curl, scripts) are as trusted here as they are on any REST endpoint.
"""
from __future__ import annotations

import asyncio
import sqlite3

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

import settings

router = APIRouter(tags=["System"])

POLL_SECONDS = 5.0


@router.websocket("/ws")
async def live_updates(ws: WebSocket) -> None:
    origin = ws.headers.get("origin")
    if origin is not None and origin not in settings.CORS_ORIGINS:
        await ws.close(code=1008)  # policy violation
        return
    await ws.accept()

    # PRAGMA data_version increments whenever another connection commits, and
    # the scheduler lives in another *process* — so a private long-lived
    # connection polling it is the cross-process change signal, no bus needed.
    conn = sqlite3.connect(settings.DB_PATH, timeout=15.0)
    try:
        version = conn.execute("PRAGMA data_version").fetchone()[0]
        while True:
            await asyncio.sleep(POLL_SECONDS)
            current = conn.execute("PRAGMA data_version").fetchone()[0]
            if current != version:
                version = current
                await ws.send_json({"type": "changed"})
    # ponytail: a silently-vanished client is only noticed at the next send or
    # uvicorn's ws ping (20s default); add a reader task if that ever matters.
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        conn.close()

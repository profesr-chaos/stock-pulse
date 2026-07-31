"""The /ws live-update channel: origin gate and change push."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

import db
import settings
from routes import ws as ws_route


def test_rejects_unlisted_origin(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}):
            pass
    assert exc.value.code == 1008


def test_pushes_on_db_change(client, monkeypatch):
    monkeypatch.setattr(ws_route, "POLL_SECONDS", 0.05)
    origin = settings.CORS_ORIGINS[0]
    with client.websocket_connect("/ws", headers={"origin": origin}) as ws:
        # A commit on any other connection must bump data_version and push.
        db.watchlist.add("TSLA")
        assert ws.receive_json() == {"type": "changed"}

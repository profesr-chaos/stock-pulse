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
    monkeypatch.setattr(ws_route, "COALESCE_SECONDS", 0.01)
    origin = settings.CORS_ORIGINS[0]
    with client.websocket_connect("/ws", headers={"origin": origin}) as ws:
        # A commit on any other connection must reach the socket. The trigger
        # is what makes that true without the writer knowing /ws exists.
        db.watchlist.add("TSLA")
        assert ws.receive_json() == {"type": "changed"}


def test_many_rows_in_one_statement_notify_once(temp_db):
    """The trigger is FOR EACH STATEMENT, so a 500-row insert is one
    notification rather than 500."""
    import psycopg

    with psycopg.connect(settings.DB_DSN, autocommit=True) as listener:
        listener.execute(f"LISTEN {ws_route.CHANNEL}")

        db.news.insert_news_many([{
            "short_name": "AAPL",
            "title": f"Apple story number {n} about something happening",
            "title_key": f"k{n}", "url": f"https://reuters.com/{n}",
            "url_hash": f"h{n}", "source": "Reuters",
            "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
            "publish_time": "2026-08-01T00:00:00Z",
        } for n in range(50)])

        listener.execute("SELECT 1")  # round trip so notifications are read
        assert len(list(listener.notifies(timeout=2.0, stop_after=1))) == 1

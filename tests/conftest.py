"""Shared fixtures.

Every test runs against a throwaway SQLite file and never touches the network:
anything that would scrape is patched at the seam. That keeps the suite fast and
means a failing test is a real bug, not a flaky third party.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import settings  # noqa: E402
from db import connection  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """A fresh, migrated database for one test."""
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(connection, "_initialised", False)
    db.create_tables()
    return tmp_path / "test.db"


@pytest.fixture
def stocked_db(temp_db):
    """A DB with a few instruments and a watchlist, resolved and priced."""
    db.stocks.bulk_upsert_stocks([
        {"shortName": "AAPL", "name": "Apple", "type": "STOCK", "currencyCode": "USD"},
        {"shortName": "TSLA", "name": "Tesla", "type": "STOCK", "currencyCode": "EUR"},
        {"shortName": "6RJ0", "name": "Rocket Lab Corp", "type": "STOCK", "currencyCode": "EUR"},
        {"shortName": "SHEL", "name": "Shell", "type": "STOCK", "currencyCode": "GBX"},
    ])
    db.stocks.set_resolution("AAPL", "AAPL", "NMS", "USD")
    db.stocks.set_resolution("6RJ0", "RKLB", "NMS", "USD")
    db.stocks.bulk_set_quotes([
        {"short_name": "AAPL", "price": 338.19, "change": -1.89,
         "change_percent": -0.556, "currency": "USD"},
    ])
    db.watchlist.add("AAPL")
    db.watchlist.add("6RJ0")
    return temp_db


@pytest.fixture
def client(stocked_db, monkeypatch):
    """FastAPI TestClient with all network paths stubbed out."""
    from fastapi.testclient import TestClient

    import jobs
    import main
    from services import prices

    monkeypatch.setattr(jobs, "catch_up", lambda: {"backfilled": []})
    monkeypatch.setattr(jobs, "backfill_stock", lambda *a, **kw: {"skipped": "test"})
    # Only the network call is stubbed. prices.get_series still reads the DB,
    # so route tests exercise the real query.
    monkeypatch.setattr(prices, "refresh_stock", lambda *a, **kw: None)

    with TestClient(main.app) as test_client:
        yield test_client


def article(**overrides) -> dict:
    """A scraped-article dict with sensible defaults, for dedup tests."""
    from normalize import now_utc

    base = {
        "title": "Apple beats Q3 estimates as iPhone revenue tops forecasts",
        "url": "https://reuters.com/tech/apple-q3",
        "published_at": now_utc(),
        "description": None,
        "image": None,
        "source": "Reuters",
        "source_domain": "reuters.com",
        "source_type": "GOOGLE_NEWS",
    }
    base.update(overrides)
    return base

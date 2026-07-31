"""Shared fixtures.

Every test runs against a throwaway Postgres schema and never touches the
network: anything that would scrape is patched at the seam. That keeps the suite
fast and means a failing test is a real bug, not a flaky third party.

The suite needs a running Postgres. Point STOCKY_TEST_DSN at it if the default
below is wrong; the database it names is wiped between tests, so never aim it at
the real one.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import settings  # noqa: E402

TEST_DSN = os.getenv("STOCKY_TEST_DSN") or "postgresql://postgres@localhost:5432/stocky_test"


@pytest.fixture(scope="session", autouse=True)
def _point_at_the_test_database():
    """Session-wide, and before anything can open a pool against the real DSN."""
    settings.DB_DSN = TEST_DSN
    yield


@pytest.fixture
def temp_db():
    """An empty database for one test.

    TRUNCATE rather than drop-and-recreate: the schema is identical every time,
    so recreating it per test would just pay DDL cost ~200 times over. RESTART
    IDENTITY keeps row ids predictable across tests.
    """
    db.create_tables()
    with db.get_connection() as conn:
        conn.execute(
            "TRUNCATE stocks, news, prices, watchlist,"
            " stock_sentiment_history, stock_ai_summaries RESTART IDENTITY"
        )
    return TEST_DSN


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

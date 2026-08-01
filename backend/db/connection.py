"""Postgres connection handling and schema.

Connections come from a pool. Unlike SQLite, where "connecting" was opening a
file, a Postgres connect is a TCP round trip plus authentication — doing that
per query would cost more than most of the queries.

Timestamps are stored as ISO 8601 UTC *text*, not `timestamptz`. Every producer
(scrapers, normalize.py) and every consumer (routes, the frontend) already
speaks that string, and string comparison on a fixed-width ISO format sorts and
ranges identically. `ponytail: TEXT timestamps — switch to timestamptz when
something needs real date arithmetic in SQL.`

Surrogate keys are UUIDv7 via Postgres 18's built-in `uuidv7()` — **this schema
needs PG 18 or newer**, there is no extension fallback. v7 rather than v4
because the timestamp lives in the leading bytes, so ids sort chronologically
and inserts land at the right-hand edge of the B-tree instead of scattering
across it the way v4 does. That ordering is also what keeps `ORDER BY
publish_time DESC, id DESC` a meaningful tiebreaker rather than a random one.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

import settings

_pool_lock = threading.Lock()
_pools: dict[str, ConnectionPool] = {}

# Arbitrary but fixed: the API and the scheduler both run create_tables() on
# start, and concurrent CREATE TABLE IF NOT EXISTS can collide in the catalogue.
_SCHEMA_LOCK_ID = 0x570C6D


def _pool() -> ConnectionPool:
    """One pool per DSN. Keyed rather than global so tests can point at another
    database without leaving a pool bound to the old one."""
    dsn = settings.DB_DSN
    with _pool_lock:
        pool = _pools.get(dsn)
        if pool is None:
            pool = _pools[dsn] = ConnectionPool(
                dsn,
                min_size=1,
                max_size=settings.DB_POOL_SIZE,
                kwargs={"row_factory": dict_row},
                open=True,
            )
        return pool


@contextmanager
def get_connection():
    """A pooled connection: committed on success, rolled back on exception,
    returned to the pool either way."""
    with _pool().connection() as conn:
        yield conn


def rows(cursor) -> list[dict]:
    return cursor.fetchall()


def one(cursor) -> dict | None:
    return cursor.fetchone()


def executemany(conn, sql: str, params_seq) -> int:
    """psycopg puts executemany on the cursor, not the connection. Returns the
    total number of rows affected across the batch."""
    cur = conn.cursor()
    cur.executemany(sql, params_seq)
    return cur.rowcount


# ── Schema ───────────────────────────────────────────────────────────────

_NOW = """to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')"""

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS stocks (
    -- ponytail: nothing reads stocks.id — short_name is the real key and every
    -- join uses it. Kept only so the three tables agree; safe to drop.
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    created_at            TEXT NOT NULL DEFAULT {_NOW},
    short_name            TEXT NOT NULL,
    name                  TEXT NOT NULL,
    currency_code         TEXT,
    type                  TEXT NOT NULL,
    -- Yahoo's taxonomy, captured during symbol resolution. `sector` is the
    -- coarse bucket ("Industrials"); `industry` is what people actually mean
    -- by a sector in conversation ("Aerospace & Defense" is the space one).
    sector                TEXT,
    industry              TEXT,
    -- resolved best listing for this instrument (see services/symbols.py)
    yahoo_symbol          TEXT,
    exchange              TEXT,
    quote_currency        TEXT,
    resolved_at           TEXT,
    -- latest quote
    price                 DOUBLE PRECISION,
    price_change          DOUBLE PRECISION,
    price_change_percent  DOUBLE PRECISION,
    price_updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS news (
    id             UUID PRIMARY KEY DEFAULT uuidv7(),
    created_at     TEXT NOT NULL DEFAULT {_NOW},
    short_name     TEXT NOT NULL,
    source         TEXT NOT NULL,
    source_url     TEXT,
    source_domain  TEXT,
    source_country TEXT,
    source_type    TEXT NOT NULL,
    lang           TEXT,
    publish_time   TEXT NOT NULL,           -- ISO 8601 UTC, always
    url            TEXT NOT NULL,
    url_hash       TEXT,
    image          TEXT,
    title          TEXT NOT NULL,
    title_key      TEXT,
    description    TEXT,
    sentiment      DOUBLE PRECISION,
    ai_summary     TEXT,
    -- 'direct' names the stock; 'related' is sector context from a
    -- symbol-keyed source that never names it
    relevance      TEXT NOT NULL DEFAULT 'direct',
    -- 'high' | 'medium' | 'low', judged by the event layer. NULL means
    -- unjudged (predates the feature, or the LLM was unavailable) — which is
    -- deliberately distinct from a judged 'low'.
    impact         TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    short_name  TEXT NOT NULL,
    ts          TEXT NOT NULL,              -- ISO 8601 UTC
    close       DOUBLE PRECISION NOT NULL,
    interval    TEXT NOT NULL DEFAULT '1d', -- '1d' daily bar | 'snap' hourly snapshot
    PRIMARY KEY (short_name, ts, interval)
);

CREATE TABLE IF NOT EXISTS watchlist (
    short_name    TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL DEFAULT {_NOW},
    position      INTEGER NOT NULL DEFAULT 0,
    backfilled_at TEXT                      -- NULL until the history backfill finished
);

CREATE TABLE IF NOT EXISTS stock_sentiment_history (
    short_name     TEXT NOT NULL,
    date           TEXT NOT NULL,           -- YYYY-MM-DD UTC
    avg_sentiment  DOUBLE PRECISION,
    article_count  INTEGER,
    positive_count INTEGER,
    negative_count INTEGER,
    neutral_count  INTEGER,
    created_at     TEXT NOT NULL DEFAULT {_NOW},
    PRIMARY KEY (short_name, date)
);

CREATE TABLE IF NOT EXISTS stock_ai_summaries (
    id            UUID PRIMARY KEY DEFAULT uuidv7(),
    created_at    TEXT NOT NULL DEFAULT {_NOW},
    short_name    TEXT NOT NULL,
    ai_summary    TEXT NOT NULL,
    tokens_total  INTEGER NOT NULL DEFAULT 0,
    days          INTEGER NOT NULL DEFAULT 7,
    article_count INTEGER NOT NULL DEFAULT 0
);

-- What actually happened, as opposed to what was written about. One row per
-- materially new development, judged against the coverage already stored.
CREATE TABLE IF NOT EXISTS events (
    id               UUID PRIMARY KEY DEFAULT uuidv7(),
    created_at       TEXT NOT NULL DEFAULT {_NOW},
    short_name       TEXT NOT NULL,
    headline         TEXT NOT NULL,   -- what's new, one line
    why_it_matters   TEXT NOT NULL,
    previously_known TEXT,            -- NULL when genuinely fresh
    impact           TEXT NOT NULL,   -- 'high' | 'medium' | 'low'
    news_ids         UUID[] NOT NULL, -- backing articles
    tokens_total     INTEGER NOT NULL DEFAULT 0
);

-- CREATE TABLE IF NOT EXISTS leaves an existing table alone, so a new column
-- on an old database needs its own idempotent statement or the app runs on the
-- old shape while the tests pass.
ALTER TABLE news ADD COLUMN IF NOT EXISTS impact TEXT;
"""

_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_stocks_short_name ON stocks(short_name);
CREATE INDEX        IF NOT EXISTS idx_stocks_name       ON stocks(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_news_stock_url    ON news(short_name, url_hash);
CREATE INDEX        IF NOT EXISTS idx_news_stock_time   ON news(short_name, publish_time DESC);
CREATE INDEX        IF NOT EXISTS idx_news_time         ON news(publish_time DESC);
CREATE INDEX        IF NOT EXISTS idx_news_stock_key    ON news(short_name, title_key);
CREATE INDEX        IF NOT EXISTS idx_prices_stock_ts   ON prices(short_name, ts);
CREATE INDEX        IF NOT EXISTS idx_summaries_stock   ON stock_ai_summaries(short_name, created_at DESC);
CREATE INDEX        IF NOT EXISTS idx_events_stock_time  ON events(short_name, created_at DESC);
"""


def create_tables() -> None:
    """Idempotent: safe on every start, and safe when the API and the scheduler
    do it at the same moment."""
    with get_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_ID,))
        conn.execute(_SCHEMA)
        conn.execute(_INDEXES)

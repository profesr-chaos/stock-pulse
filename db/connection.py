"""SQLite connection handling, schema, and in-place migration.

One connection per call, closed on exit. WAL plus a busy timeout is enough
concurrency control for one API process, a scheduler process and a handful of
background threads.
"""
from __future__ import annotations

import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import settings
from normalize import domain_of, parse_datetime, title_key, to_iso, url_hash

_init_lock = threading.Lock()
_initialised = False


@contextmanager
def get_connection():
    """A committed-on-success, always-closed connection.

    `with sqlite3.connect(...)` alone commits but never closes, which leaked a
    connection on every single query in the previous version.
    """
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def one(cursor) -> dict | None:
    r = cursor.fetchone()
    return dict(r) if r else None


# ── Schema ───────────────────────────────────────────────────────────────

_NOW = "(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS stocks (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at            TEXT NOT NULL DEFAULT {_NOW},
    short_name            TEXT NOT NULL,
    name                  TEXT NOT NULL,
    currency_code         TEXT,
    type                  TEXT NOT NULL,
    industry              TEXT,
    -- resolved best listing for this instrument (see services/symbols.py)
    yahoo_symbol          TEXT,
    exchange              TEXT,
    quote_currency        TEXT,
    resolved_at           TEXT,
    -- latest quote
    price                 REAL,
    price_change          REAL,
    price_change_percent  REAL,
    price_updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS news (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
    sentiment      REAL,
    ai_summary     TEXT,
    -- 'direct' names the stock; 'related' is sector context from a
    -- symbol-keyed source that never names it
    relevance      TEXT NOT NULL DEFAULT 'direct'
);

CREATE TABLE IF NOT EXISTS prices (
    short_name  TEXT NOT NULL,
    ts          TEXT NOT NULL,              -- ISO 8601 UTC
    close       REAL NOT NULL,
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
    avg_sentiment  REAL,
    article_count  INTEGER,
    positive_count INTEGER,
    negative_count INTEGER,
    neutral_count  INTEGER,
    created_at     TEXT NOT NULL DEFAULT {_NOW},
    PRIMARY KEY (short_name, date)
);

CREATE TABLE IF NOT EXISTS stock_ai_summaries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL DEFAULT {_NOW},
    short_name    TEXT NOT NULL,
    ai_summary    TEXT NOT NULL,
    tokens_total  INTEGER NOT NULL DEFAULT 0,
    days          INTEGER NOT NULL DEFAULT 7,
    article_count INTEGER NOT NULL DEFAULT 0
);
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
"""

# Columns added after the original release. Guarded ALTER TABLE ADD COLUMN is
# cheap and idempotent, so this doubles as the migration for existing DBs.
_ADDED_COLUMNS = [
    ("stocks", "yahoo_symbol", "TEXT"),
    ("stocks", "exchange", "TEXT"),
    ("stocks", "quote_currency", "TEXT"),
    ("stocks", "resolved_at", "TEXT"),
    ("stocks", "price_updated_at", "TEXT"),
    ("news", "url_hash", "TEXT"),
    ("news", "title_key", "TEXT"),
    ("news", "source_domain", "TEXT"),
    ("news", "relevance", "TEXT NOT NULL DEFAULT 'direct'"),
    ("stock_ai_summaries", "article_count", "INTEGER NOT NULL DEFAULT 0"),
]

# Auth, tiers and payments are gone.
_DROPPED_TABLES = ["users", "user_industries", "user_stocks"]
_DROPPED_COLUMNS = [("stocks", "in_free_tier"), ("stocks", "in_use")]


def _columns(conn, table: str) -> set[str]:
    try:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    )


def _relocate_legacy_db() -> None:
    """Older builds kept stocky.db in the repo root; WAL wants its own dir."""
    legacy = settings.ROOT / "stocky.db"
    if settings.DB_PATH.exists() or not legacy.exists():
        return
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(settings.DB_PATH))
    for suffix in ("-wal", "-shm"):
        side = Path(str(legacy) + suffix)
        if side.exists():
            shutil.move(str(side), str(settings.DB_PATH) + suffix)
    print(f"[db] moved legacy {legacy.name} -> {settings.DB_PATH}")


def create_tables() -> None:
    """Idempotent: safe on every start. Creates, migrates, then indexes."""
    global _initialised
    with _init_lock:
        _relocate_legacy_db()
        with get_connection() as conn:
            conn.executescript(_SCHEMA)
            _migrate(conn)
            conn.executescript(_INDEXES)
        _initialised = True


def ensure_initialised() -> None:
    if not _initialised:
        create_tables()


def _migrate(conn) -> None:
    for table, column, decl in _ADDED_COLUMNS:
        if _table_exists(conn, table) and column not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            print(f"[db] added {table}.{column}")

    _migrate_watchlist(conn)
    _repair_consent_urls(conn)
    _backfill_news_keys(conn)
    _dedupe_stocks(conn)
    _dedupe_news(conn)
    _migrate_sentiment_history(conn)
    _drop_legacy(conn)


def _migrate_watchlist(conn) -> None:
    """Fold the multi-user user_stocks table into the single-user watchlist."""
    if not _table_exists(conn, "user_stocks"):
        return
    # COALESCE matters: a legacy row with a NULL created_at would violate the
    # NOT NULL column and be silently swallowed by OR IGNORE, losing the follow.
    moved = conn.execute(f"""
        INSERT OR IGNORE INTO watchlist (short_name, created_at, position)
        SELECT short_name,
               COALESCE(MIN(created_at), {_NOW}),
               COALESCE(MIN(position), 0)
        FROM user_stocks
        WHERE short_name IS NOT NULL
        GROUP BY short_name
    """).rowcount
    if moved:
        print(f"[db] migrated {moved} watchlist entries from user_stocks")


def _repair_consent_urls(conn) -> None:
    """Unwrap Google's cookie-consent interstitial from stored article URLs.

    The previous scraper followed each Google News redirect to "resolve" the
    real link, but an unauthenticated fetch lands on
    `consent.google.com/ml?continue=<real url>` — so that is what got saved, and
    those links open a cookie prompt instead of the article. The `continue`
    parameter still holds the working URL, so unwrap it in place.
    """
    from urllib.parse import parse_qs, unquote, urlsplit

    broken = conn.execute(
        "SELECT id, url FROM news WHERE url LIKE 'https://consent.google.com/%'"
    ).fetchall()
    if not broken:
        return

    updates = []
    for row in broken:
        target = parse_qs(urlsplit(row["url"]).query).get("continue", [None])[0]
        if target:
            target = unquote(target)
            updates.append((target, url_hash(target), domain_of(target), row["id"]))

    if updates:
        # OR IGNORE: unwrapping can collide with a copy we already hold for the
        # same stock, and the uniqueness index should win over the repair.
        conn.executemany(
            "UPDATE OR IGNORE news SET url = ?, url_hash = ?, source_domain = ? WHERE id = ?",
            updates,
        )

    # Anything still pointing at the consent page has no recoverable target (or
    # lost a uniqueness collision). A link that opens a cookie prompt is worse
    # than no row, so drop it.
    dropped = conn.execute(
        "DELETE FROM news WHERE url LIKE 'https://consent.google.com/%'"
    ).rowcount
    print(f"[db] unwrapped {len(updates) - dropped} Google consent-page URLs"
          f"{f', dropped {dropped} unrecoverable' if dropped else ''}")


def _backfill_news_keys(conn) -> None:
    """Populate url_hash/title_key/source_domain and normalise publish_time.

    Old rows stored RFC-822 dates verbatim (`Wed, 28 Jan 2026 22:07:57 +0000`),
    so ORDER BY and `since` comparisons sorted nonsense and date(publish_time)
    returned NULL — which is why sentiment aggregation produced almost nothing.
    """
    pending = conn.execute("""
        SELECT id, url, title, publish_time, source_url
        FROM news
        WHERE url_hash IS NULL OR title_key IS NULL
           OR publish_time NOT LIKE '____-__-__T%Z'
    """).fetchall()
    if not pending:
        return

    updates = []
    for r in pending:
        parsed = parse_datetime(r["publish_time"])
        updates.append((
            url_hash(r["url"]),
            title_key(r["title"] or ""),
            domain_of(r["url"]) or domain_of(r["source_url"] or ""),
            to_iso(parsed) if parsed else r["publish_time"],
            r["id"],
        ))

    conn.executemany(
        "UPDATE news SET url_hash=?, title_key=?, source_domain=?, publish_time=? WHERE id=?",
        updates,
    )
    print(f"[db] normalised {len(updates)} news rows")


def _dedupe_stocks(conn) -> None:
    """The unique index on short_name cannot be built until dupes are gone."""
    removed = conn.execute("""
        DELETE FROM stocks WHERE id NOT IN (
            SELECT MIN(id) FROM stocks GROUP BY short_name
        )
    """).rowcount
    if removed:
        print(f"[db] removed {removed} duplicate stock rows")


def _dedupe_news(conn) -> None:
    """Same, for the (short_name, url_hash) key. Keeps the richest copy of each
    article: one with a description first, then one with an image."""
    removed = conn.execute("""
        DELETE FROM news WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY short_name, url_hash
                    ORDER BY (description IS NULL), (image IS NULL), id
                ) AS rn
                FROM news
            ) WHERE rn = 1
        )
    """).rowcount
    if removed:
        print(f"[db] removed {removed} duplicate news rows")


def _migrate_sentiment_history(conn) -> None:
    """The old table carried a surrogate id; the new one is keyed on
    (short_name, date). Rebuild only if the old shape is still there."""
    cols = _columns(conn, "stock_sentiment_history")
    if "id" not in cols:
        return
    conn.executescript(f"""
        CREATE TABLE _ssh_new (
            short_name     TEXT NOT NULL,
            date           TEXT NOT NULL,
            avg_sentiment  REAL,
            article_count  INTEGER,
            positive_count INTEGER,
            negative_count INTEGER,
            neutral_count  INTEGER,
            created_at     TEXT NOT NULL DEFAULT {_NOW},
            PRIMARY KEY (short_name, date)
        );
        INSERT OR REPLACE INTO _ssh_new
            (short_name, date, avg_sentiment, article_count, positive_count,
             negative_count, neutral_count, created_at)
        SELECT short_name, date, avg_sentiment, article_count, positive_count,
               negative_count, neutral_count, created_at
        FROM stock_sentiment_history;
        DROP TABLE stock_sentiment_history;
        ALTER TABLE _ssh_new RENAME TO stock_sentiment_history;
    """)
    print("[db] rebuilt stock_sentiment_history without surrogate id")


def _drop_legacy(conn) -> None:
    for table in _DROPPED_TABLES:
        if _table_exists(conn, table):
            conn.execute(f"DROP TABLE {table}")
            print(f"[db] dropped {table}")

    for table, column in _DROPPED_COLUMNS:
        if column in _columns(conn, table):
            try:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
                print(f"[db] dropped {table}.{column}")
            except sqlite3.OperationalError:
                pass  # older sqlite: harmless to leave the column behind

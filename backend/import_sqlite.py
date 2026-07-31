"""One-shot: copy the old SQLite database into Postgres.

    python import_sqlite.py [path/to/stocky.db]

Run it once, against an empty Postgres database, after `create_tables()`. It is
not a migration framework and it is not idempotent by design — it refuses to
run if the target already holds rows, because "import again" is nearly always a
mistake and a silent double-import is worse than an error.

Delete this file once the old .db is gone.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import db
import settings
from db.connection import executemany

# Same order as the schema; children have no FKs, so order only affects output.
#
# `id` is deliberately absent everywhere. The old ids were 32-bit integers and
# the new ones are UUIDv7, so there is nothing to carry over — every row gets a
# fresh id from the column default. Nothing outside the database holds a news
# id (the frontend only keeps them for the lifetime of a page), so renumbering
# costs nothing.
TABLES = {
    "stocks": (
        "created_at short_name name currency_code type sector industry "
        "yahoo_symbol exchange quote_currency resolved_at price price_change "
        "price_change_percent price_updated_at"
    ).split(),
    "news": (
        "created_at short_name source source_url source_domain source_country "
        "source_type lang publish_time url url_hash image title title_key "
        "description sentiment ai_summary relevance"
    ).split(),
    "prices": "short_name ts close interval".split(),
    "watchlist": "short_name created_at position backfilled_at".split(),
    "stock_sentiment_history": (
        "short_name date avg_sentiment article_count positive_count "
        "negative_count neutral_count created_at"
    ).split(),
    "stock_ai_summaries": (
        "created_at short_name ai_summary tokens_total days article_count"
    ).split(),
}

_BATCH = 2000


def _source_columns(src: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """(name in SQLite, name in Postgres) for each column worth copying.

    Two things make this fiddlier than a set intersection:

    - Only copy columns the old database actually has, so a .db from before a
      column was added doesn't blow up on a missing key.
    - Match case-insensitively. SQLite resolves column names without regard to
      case, so `news.AI_summary` answered to `ai_summary` in every query and
      nobody ever noticed the declared name kept its legacy capitals. Postgres
      folds to lowercase, and a case-sensitive comparison here silently skips
      the column — dropping every stored article summary.
    """
    have = {r[1].lower(): r[1] for r in src.execute(f"PRAGMA table_info({table})")}
    return [(have[c], c) for c in TABLES[table] if c in have]


def import_from(sqlite_path: Path) -> dict[str, int]:
    if not sqlite_path.exists():
        raise SystemExit(f"no such file: {sqlite_path}")

    db.create_tables()
    counts: dict[str, int] = {}

    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        with db.get_connection() as dst:
            for table in TABLES:
                if dst.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    raise SystemExit(
                        f"{table} already has rows in {settings.db_label()} — "
                        "import into an empty database, or drop it first"
                    )

            for table in TABLES:
                cols = _source_columns(src, table)
                marks = ",".join(["%s"] * len(cols))
                sql = (f"INSERT INTO {table} ({','.join(pg for _, pg in cols)})"
                       f" VALUES ({marks})")
                cur = src.execute(
                    f"SELECT {','.join(f'\"{lite}\"' for lite, _ in cols)} FROM {table}"
                )
                moved = 0
                while batch := cur.fetchmany(_BATCH):
                    executemany(dst, sql, [tuple(r) for r in batch])
                    moved += len(batch)
                counts[table] = moved
                print(f"[import] {table}: {moved}")
    finally:
        src.close()

    return counts


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else settings.ROOT / "data" / "stocky.db"
    print(f"[import] {path} -> {settings.db_label()}")
    total = import_from(path)
    print(f"[import] done: {sum(total.values())} rows")

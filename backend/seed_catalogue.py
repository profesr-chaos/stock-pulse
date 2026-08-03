"""Load `seed/catalogue.json` into the stocks table.

Runs automatically on a fresh database (see `seed_if_empty`), so a clone starts
with working local search instead of an empty catalogue. Still optional: the
app works from nothing — search falls through to Yahoo and following writes the
row — and `STOCKY_SEED_ON_START=0` turns the automatic pass off. Idempotent, so
re-running refreshes names and inserts whatever is new.

    python seed_catalogue.py [path/to/catalogue.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import db
import settings

CATALOGUE = Path(__file__).resolve().parent / "seed" / "catalogue.json"


def seed(path: Path = CATALOGUE) -> int:
    instruments = [
        {
            "shortName": row["symbol"],
            "name": row["name"],
            "type": row["type"],
            # "" would win over the quote's own currency in `to_stock`, so an
            # absent currency has to reach the DB as NULL, not as a blank.
            "currencyCode": row.get("currency") or None,
        }
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]

    db.create_tables()
    inserted = db.stocks.bulk_upsert_stocks(instruments)
    print(f"[seed] {len(instruments)} in {path.name}, {inserted} new, "
          f"{db.stocks.count_stocks()} in the catalogue")
    return inserted


def seed_if_empty() -> int:
    """Seed a fresh database on startup, once.

    Any existing row means the user has a catalogue already — seeded before, or
    built by following stocks — and re-upserting ten thousand rows on every boot
    would buy nothing. Never raises: a missing or malformed seed file must
    degrade to "local search is thin until you follow something", not stop the
    API from starting.
    """
    if not settings.SEED_ON_START or not CATALOGUE.exists():
        return 0
    try:
        if db.stocks.count_stocks():
            return 0
        # Explicitly, not via `seed`'s default: a default argument binds at
        # definition time, so overriding the module's CATALOGUE would be
        # silently ignored.
        return seed(CATALOGUE)
    except Exception as exc:
        print(f"[seed] skipped: {type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    seed(Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOGUE)

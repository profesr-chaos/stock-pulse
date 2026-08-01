"""The watchlist. One user, so no user_id anywhere."""
from __future__ import annotations

from normalize import now_iso

from .connection import executemany, get_connection, rows


def get_symbols() -> list[str]:
    with get_connection() as conn:
        return [r["short_name"] for r in conn.execute(
            "SELECT short_name FROM watchlist ORDER BY position ASC, created_at ASC"
        )]


def get_watchlist() -> list[dict]:
    """Watchlist joined with catalogue + quote, in display order.

    LEFT JOIN so a symbol that isn't in the instrument catalogue still shows up
    rather than silently vanishing from the list.
    """
    with get_connection() as conn:
        return rows(conn.execute("""
            SELECT w.short_name, w.position, w.created_at, w.backfilled_at,
                   s.name, s.type, s.industry, s.currency_code, s.quote_currency,
                   s.yahoo_symbol, s.exchange,
                   s.price, s.price_change, s.price_change_percent, s.price_updated_at
            FROM watchlist w
            LEFT JOIN stocks s ON s.short_name = w.short_name
            ORDER BY w.position ASC, w.created_at ASC
        """))


def is_following(short_name: str) -> bool:
    with get_connection() as conn:
        return bool(conn.execute(
            "SELECT 1 FROM watchlist WHERE short_name = %s", (short_name,)
        ).fetchone())


def add(short_name: str) -> bool:
    """False if already present."""
    with get_connection() as conn:
        next_pos = conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS p FROM watchlist"
        ).fetchone()["p"]
        cur = conn.execute(
            "INSERT INTO watchlist (short_name, position) VALUES (%s, %s)"
            " ON CONFLICT (short_name) DO NOTHING",
            (short_name, next_pos),
        )
        return cur.rowcount > 0


def remove(short_name: str) -> bool:
    with get_connection() as conn:
        return conn.execute(
            "DELETE FROM watchlist WHERE short_name = %s", (short_name,)
        ).rowcount > 0


def reorder(ordered: list[str]) -> None:
    with get_connection() as conn:
        executemany(
            conn,
            "UPDATE watchlist SET position = %s WHERE short_name = %s",
            [(i, name) for i, name in enumerate(ordered)],
        )


def mark_backfilled(short_name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE watchlist SET backfilled_at = %s WHERE short_name = %s",
            (now_iso(), short_name),
        )


def needing_backfill() -> list[str]:
    with get_connection() as conn:
        return [r["short_name"] for r in conn.execute(
            "SELECT short_name FROM watchlist WHERE backfilled_at IS NULL ORDER BY position"
        )]

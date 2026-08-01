"""Price history.

Two kinds of row share the table, distinguished by `interval`:
  '1d'   — official daily close, timestamped at midnight UTC
  'snap' — whatever the price was at an hourly refresh

Daily bars give the 1-month chart; snapshots give intraday shape for the last
day or two without paying for a real intraday feed.
"""
from __future__ import annotations

from .connection import executemany, get_connection, one, rows


def upsert_points(short_name: str, points: list[tuple[str, float]], interval: str = "1d") -> int:
    """points = [(iso_ts, close)]. Re-running a backfill is a no-op."""
    if not points:
        return 0
    with get_connection() as conn:
        return executemany(conn, """
            INSERT INTO prices (short_name, ts, close, interval)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(short_name, ts, interval) DO UPDATE SET close = excluded.close
        """, [(short_name, ts, close, interval) for ts, close in points if close is not None])


def get_history(short_name: str, since: str, interval: str | None = None) -> list[dict]:
    where, params = ["short_name = %s", "ts >= %s"], [short_name, since]
    if interval:
        where.append("interval = %s")
        params.append(interval)
    with get_connection() as conn:
        return rows(conn.execute(
            f"SELECT ts, close, interval FROM prices WHERE {' AND '.join(where)} ORDER BY ts ASC",
            params,
        ))


def get_series(short_name: str, since: str) -> list[dict]:
    """Chart series: daily bars, plus snapshots for days with no bar yet (today
    and any day the daily feed hasn't published)."""
    with get_connection() as conn:
        return rows(conn.execute("""
            SELECT ts, close FROM prices
            WHERE short_name = %s AND ts >= %s
              AND (interval = '1d' OR substr(ts, 1, 10) NOT IN (
                    SELECT substr(ts, 1, 10) FROM prices
                    WHERE short_name = %s AND interval = '1d' AND ts >= %s
              ))
            ORDER BY ts ASC
        """, (short_name, since, short_name, since)))


def latest(short_name: str) -> dict | None:
    with get_connection() as conn:
        return one(conn.execute(
            "SELECT ts, close FROM prices WHERE short_name = %s ORDER BY ts DESC LIMIT 1",
            (short_name,),
        ))


def close_on_or_before(short_name: str, ts: str) -> dict | None:
    """Used for "change over the last N days" without a second network call."""
    with get_connection() as conn:
        return one(conn.execute("""
            SELECT ts, close FROM prices
            WHERE short_name = %s AND ts <= %s
            ORDER BY ts DESC LIMIT 1
        """, (short_name, ts)))


def delete_older_than(cutoff_iso: str) -> int:
    with get_connection() as conn:
        return conn.execute("DELETE FROM prices WHERE ts < %s", (cutoff_iso,)).rowcount

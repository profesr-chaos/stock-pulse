"""Daily sentiment rollups.

Grouping uses substr(publish_time, 1, 10) rather than date(publish_time): it is
version-independent and, more importantly, it only works at all now that
publish_time is guaranteed to be ISO 8601. The old table stored raw RFC-822
strings, so date() returned NULL and almost nothing aggregated.
"""
from __future__ import annotations

from normalize import day_str, days_ago_iso

from .connection import get_connection, rows

_POSITIVE = 0.2
_NEGATIVE = -0.2


def aggregate_day(date: str | None = None) -> int:
    """Roll one UTC day of scored articles into stock_sentiment_history."""
    date = date or day_str()
    with get_connection() as conn:
        return conn.execute(f"""
            INSERT INTO stock_sentiment_history
                (short_name, date, avg_sentiment, article_count,
                 positive_count, negative_count, neutral_count)
            SELECT short_name, ?, AVG(sentiment), COUNT(*),
                   SUM(sentiment >  {_POSITIVE}),
                   SUM(sentiment <  {_NEGATIVE}),
                   SUM(sentiment BETWEEN {_NEGATIVE} AND {_POSITIVE})
            FROM news
            WHERE substr(publish_time, 1, 10) = ? AND sentiment IS NOT NULL
            GROUP BY short_name
            ON CONFLICT(short_name, date) DO UPDATE SET
                avg_sentiment  = excluded.avg_sentiment,
                article_count  = excluded.article_count,
                positive_count = excluded.positive_count,
                negative_count = excluded.negative_count,
                neutral_count  = excluded.neutral_count
        """, (date, date)).rowcount


def aggregate_all(days: int = 60) -> int:
    """Rebuild every day in the window. Cheap enough to just redo it, which
    also picks up sentiment scored after the fact."""
    with get_connection() as conn:
        dates = [r["d"] for r in conn.execute("""
            SELECT DISTINCT substr(publish_time, 1, 10) AS d
            FROM news
            WHERE sentiment IS NOT NULL AND publish_time >= ?
            ORDER BY d
        """, (days_ago_iso(days),))]
    return sum(aggregate_day(d) for d in dates)


def get_history(short_name: str, days: int = 30) -> list[dict]:
    with get_connection() as conn:
        return rows(conn.execute("""
            SELECT * FROM stock_sentiment_history
            WHERE short_name = ? AND date >= ?
            ORDER BY date ASC
        """, (short_name, day_str_days_ago(days))))


def day_str_days_ago(days: int) -> str:
    return days_ago_iso(days)[:10]


def get_deltas(short_names: list[str], window_days: int = 3, baseline_days: int = 14) -> list[dict]:
    """Recent sentiment vs the preceding baseline, per stock.

    Feeds the "sentiment up 18%" style panels: a stock whose coverage just
    turned negative is far more interesting than one that is quietly negative
    all the time.
    """
    if not short_names:
        return []
    marks = ",".join("?" * len(short_names))
    recent_from = day_str_days_ago(window_days)
    base_from = day_str_days_ago(baseline_days)
    with get_connection() as conn:
        return rows(conn.execute(f"""
            SELECT short_name,
                   AVG(CASE WHEN date >= ? THEN avg_sentiment END)                AS recent_sentiment,
                   AVG(CASE WHEN date >= ? AND date < ? THEN avg_sentiment END)   AS baseline_sentiment,
                   SUM(CASE WHEN date >= ? THEN article_count ELSE 0 END)         AS recent_articles
            FROM stock_sentiment_history
            WHERE short_name IN ({marks}) AND date >= ?
            GROUP BY short_name
        """, [recent_from, base_from, recent_from, recent_from, *short_names, base_from]))

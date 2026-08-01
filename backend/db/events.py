"""Materially new developments, one row per judged event.

Distinct from `news`: fifty articles can back one event, and a day with heavy
coverage and nothing new produces no rows at all — which is the answer the feed
could not previously give.
"""
from __future__ import annotations

from uuid import UUID

from normalize import days_ago_iso

from .connection import get_connection, rows


def insert_event(short_name: str, headline: str, why_it_matters: str,
                 impact: str, news_ids: list[UUID],
                 previously_known: str | None = None,
                 tokens_total: int = 0) -> UUID:
    with get_connection() as conn:
        return conn.execute("""
            INSERT INTO events (short_name, headline, why_it_matters,
                                previously_known, impact, news_ids, tokens_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (short_name, headline, why_it_matters, previously_known,
              impact, news_ids, tokens_total)).fetchone()["id"]


def get_events(short_names: list[str] | None = None, since: str | None = None,
               limit: int = 50) -> list[dict]:
    """Newest first. `short_names=None` means every stock; an empty list means
    none — the same distinction db.news.get_news makes, for the same reason."""
    if short_names is not None and not short_names:
        return []

    where, params = ["1=1"], []
    if short_names:
        where.append(f"short_name IN ({','.join(['%s'] * len(short_names))})")
        params += short_names
    if since:
        where.append("created_at >= %s")
        params.append(since)

    with get_connection() as conn:
        return rows(conn.execute(
            f"SELECT * FROM events WHERE {' AND '.join(where)} "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            [*params, limit],
        ))


def recent_events(short_name: str, days: int = 7, limit: int = 20) -> list[dict]:
    """Prior context for the next judgement: what we have already called an
    event for this stock."""
    return get_events([short_name], since=days_ago_iso(days), limit=limit)

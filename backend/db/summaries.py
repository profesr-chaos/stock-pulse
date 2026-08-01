"""Cached AI summaries for a stock's recent coverage."""
from __future__ import annotations

from uuid import UUID

from .connection import get_connection, one


def insert_summary(short_name: str, ai_summary: str, tokens_total: int,
                   days: int = 7, article_count: int = 0) -> UUID:
    with get_connection() as conn:
        return conn.execute("""
            INSERT INTO stock_ai_summaries (short_name, ai_summary, tokens_total, days, article_count)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (short_name, ai_summary, tokens_total, days, article_count)).fetchone()["id"]


def latest_summary(short_name: str) -> dict | None:
    with get_connection() as conn:
        return one(conn.execute("""
            SELECT * FROM stock_ai_summaries
            WHERE short_name = %s
            ORDER BY created_at DESC, id DESC LIMIT 1
        """, (short_name,)))

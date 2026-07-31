"""Health and manual refresh.

/health reports per-host scraper stats, which is the fastest way to see whether
a source is being throttled or has had its circuit opened.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

import db
import jobs
import settings
from normalize import days_ago_iso
from services import ai_service, sentiment_service
from services.http_client import scraper

from .schemas import Ok

router = APIRouter(tags=["System"])


@router.get("/health")
def health():
    watched = db.watchlist.get_symbols()
    recent = db.news.count_by_stock(since=days_ago_iso(1), short_names=watched or None)

    return {
        "ok": True,
        "database": settings.db_label(),
        "instruments": db.stocks.count_stocks(),
        "watchlist": watched,
        "articles_last_24h": sum(r["article_count"] for r in recent),
        "sentiment_backend": sentiment_service.backend(),
        "ai_summaries": "enabled" if ai_service.available() else "disabled (no DSEEK key)",
        "scrapers": scraper.stats(),
    }


@router.post("/refresh", response_model=Ok, status_code=202)
def refresh(background: BackgroundTasks):
    """Kick a full refresh in the background."""
    background.add_task(jobs.refresh_all)
    return Ok()

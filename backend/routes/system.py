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
from services import ai_service, events, sentiment_service
from services.http_client import scraper

from .schemas import AppConfig, AppConfigUpdate, Ok

router = APIRouter(tags=["System"])


def _ai_state() -> str:
    if not settings.ai_enabled():
        return "disabled (no DSEEK key)"
    if ai_service.key_rejected():
        return "disabled (key rejected)"
    return "enabled" if ai_service.available() else "disabled (switched off)"


def _config() -> AppConfig:
    flags = db.flags.get_all()
    return AppConfig(
        llmScraping=flags[db.flags.LLM_SCRAPING],
        aiSummaries=flags[db.flags.AI_SUMMARIES],
        keyPresent=settings.ai_enabled(),
        keyRejected=ai_service.key_rejected(),
        scrapingGradesImpact=events.enabled(),
        summariesAvailable=ai_service.available(),
    )


@router.get("/config", response_model=AppConfig)
def get_config():
    """The AI toggles. Nothing here gates scraping itself — only the grading."""
    return _config()


@router.put("/config", response_model=AppConfig)
def put_config(update: AppConfigUpdate):
    """Set either flag. Returns the whole resulting state, so the client never
    has to guess what the other one is now."""
    if update.llmScraping is not None:
        db.flags.set_flag(db.flags.LLM_SCRAPING, update.llmScraping)
    if update.aiSummaries is not None:
        db.flags.set_flag(db.flags.AI_SUMMARIES, update.aiSummaries)
    return _config()


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
        "ai_summaries": _ai_state(),
        "impact_grading": "enabled" if events.enabled() else "disabled",
        "scrapers": scraper.stats(),
    }


@router.post("/refresh", response_model=Ok, status_code=202)
def refresh(background: BackgroundTasks):
    """Kick a full refresh in the background."""
    background.add_task(jobs.refresh_all)
    return Ok()

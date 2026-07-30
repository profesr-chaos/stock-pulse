"""Background work: refreshes, the on-follow backfill, and rollups.

Everything here is safe to run concurrently with the API and is idempotent, so
a job that dies halfway can simply be run again.
"""
from __future__ import annotations

import json
import threading

import db
import settings
from normalize import days_ago_iso
from services import news, prices, sentiment_service
from services.http_client import scraper

# One backfill per symbol at a time. Adding a stock twice in quick succession
# would otherwise fan out two identical month-long scrapes.
_backfilling: set[str] = set()
_backfill_lock = threading.Lock()


# ── Scheduled ────────────────────────────────────────────────────────────

def refresh_prices() -> dict:
    """Hourly. Quote + recent bars for every followed stock."""
    return prices.refresh_watchlist(range_="5d")


def refresh_news() -> dict:
    """Hourly. New articles for every followed stock, then image top-up."""
    result = news.refresh_watchlist(days=2)
    sentiment_service.score_unscored()
    return result


def aggregate_sentiment() -> int:
    """Daily. Rebuild the sentiment rollups the trending panels read."""
    sentiment_service.score_unscored()
    count = db.sentiment.aggregate_all(days=settings.NEWS_RETENTION_DAYS)
    print(f"[jobs] aggregated sentiment for {count} stock-days")
    return count


def prune() -> dict:
    """Daily. Keep the DB bounded."""
    articles = news.prune()
    points = db.prices.delete_older_than(days_ago_iso(400))
    return {"articles": articles, "price_points": points}


def refresh_catalogue() -> dict:
    """Weekly, and only if Trading212 credentials exist.

    The catalogue is ~15k instruments and barely changes, so this is optional:
    without keys the app runs happily on what is already stored.
    """
    if not settings.t212_enabled():
        print("[jobs] no Trading212 credentials, skipping catalogue refresh")
        return {"inserted": 0, "skipped": True}

    instruments = _fetch_instruments()
    if not instruments:
        return {"inserted": 0, "skipped": True}

    inserted = db.stocks.bulk_upsert_stocks(instruments)
    print(f"[jobs] catalogue refreshed, {inserted} new instruments")
    return {"inserted": inserted, "skipped": False}


def _fetch_instruments() -> list[dict]:
    import base64

    token = base64.b64encode(
        f"{settings.T212_KEY}:{settings.T212_SECRET}".encode()
    ).decode()
    response = scraper.get(
        settings.T212_INSTRUMENTS_URL,
        headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
        cache=False,
    )
    if not response or not response.ok:
        print("[jobs] Trading212 instruments fetch failed")
        return []
    try:
        data = json.loads(response.text)
    except ValueError:
        return []

    allowed = {"STOCK", "ETF"}
    return [
        {
            "shortName": item.get("shortName"),
            "name": item.get("name"),
            "type": item.get("type"),
            "currencyCode": item.get("currencyCode"),
        }
        for item in data
        if isinstance(item, dict) and item.get("type") in allowed and item.get("shortName")
    ]


# ── On demand ────────────────────────────────────────────────────────────

def backfill_stock(short_name: str, days: int | None = None) -> dict:
    """Everything a newly followed stock needs, in one go.

    Runs when a stock is added so the feed is populated immediately instead of
    being empty until the next hourly tick: resolve the best listing, pull a
    month of daily prices, then a month of news.
    """
    days = days or settings.BACKFILL_DAYS

    with _backfill_lock:
        if short_name in _backfilling:
            print(f"[jobs] backfill for {short_name} already running")
            return {"short_name": short_name, "skipped": "already_running"}
        _backfilling.add(short_name)

    try:
        print(f"[jobs] backfilling {short_name}: {days}d of prices and news")
        quote = prices.refresh_stock(short_name, range_="1mo")
        article_result = news.backfill(short_name, days=days)
        db.sentiment.aggregate_all(days=days)
        db.watchlist.mark_backfilled(short_name)

        return {
            "short_name": short_name,
            "price": quote.get("price") if quote else None,
            "articles": article_result.get("inserted", 0),
            "found": article_result.get("found", 0),
        }
    except Exception as exc:
        print(f"[jobs] backfill failed for {short_name}: {type(exc).__name__}: {exc}")
        return {"short_name": short_name, "error": str(exc)}
    finally:
        with _backfill_lock:
            _backfilling.discard(short_name)


def catch_up() -> dict:
    """Run on API start: finish any backfill that never completed."""
    pending = db.watchlist.needing_backfill()
    if not pending:
        return {"backfilled": []}
    print(f"[jobs] {len(pending)} stock(s) need backfilling: {pending}")
    for short_name in pending:
        backfill_stock(short_name)
    return {"backfilled": pending}


def refresh_all() -> dict:
    """Manual full refresh, exposed on POST /refresh."""
    return {
        "prices": refresh_prices(),
        "news": refresh_news(),
        "sentiment_days": aggregate_sentiment(),
    }

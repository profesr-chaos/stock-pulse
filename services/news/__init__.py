"""News collection: fan out to every source, merge, dedupe, store, score.

Sources, in the order their copy of a story is preferred:

    Finviz        real publisher URLs, dense US coverage
    Yahoo search  thumbnails — the only free image source that costs no request
    Yahoo RSS     summaries
    Google News   the broadest reach, and the only one that can backfill a month

They are queried concurrently and merged, so a source going dark degrades
coverage instead of breaking the refresh. If every source returns nothing, that
genuinely means there is no news, not that a scraper broke — because four
independent things would have had to break at once.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import db
import settings
from normalize import days_ago_iso

from .. import dedup, sentiment_service, symbols
from . import finviz, google_news, images, yahoo_news

__all__ = ["collect", "refresh", "backfill", "refresh_watchlist", "images"]


def collect(short_name: str, company_name: str, yahoo_symbol: str | None,
            exchange: str | None, days: int = 2) -> list[dict]:
    """Every source's articles for one stock, unmerged."""
    ticker = yahoo_symbol or short_name
    us_ticker = ticker.split(".")[0]
    tasks = []

    # Google News: the only source that can reach back more than a few days.
    if days > 3:
        tasks.append(lambda: google_news.fetch_backfill(short_name, company_name, days=days))
    else:
        tasks.append(lambda: google_news.fetch_recent(short_name, company_name, days=days))

    tasks.append(lambda: yahoo_news.fetch_search(ticker))
    tasks.append(lambda: yahoo_news.fetch_rss(ticker))

    # Finviz only carries US listings.
    if symbols.is_us_listing(exchange):
        tasks.append(lambda: finviz.fetch(us_ticker))

    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="news") as pool:
        for future in [pool.submit(t) for t in tasks]:
            try:
                articles += future.result() or []
            except Exception as exc:
                print(f"[news] a source failed for {short_name}: {type(exc).__name__}: {exc}")

    return articles


def _aliases(stock: dict) -> tuple[str, ...]:
    """Other tickers this stock is known by, for relevance matching.

    Trading212 calls Rocket Lab `6RJ0`; every article calls it `RKLB`.
    """
    resolved = stock.get("yahoo_symbol") or ""
    aliases = {resolved, resolved.split(".")[0]}
    return tuple(a for a in aliases if a)


def refresh(short_name: str, days: int = 2, score: bool = True) -> dict:
    """Scrape, dedupe and store news for one stock."""
    stock = db.stocks.get_stock(short_name) or {}
    company_name = stock.get("name") or short_name

    raw = collect(
        short_name, company_name,
        stock.get("yahoo_symbol"), stock.get("exchange"),
        days=days,
    )
    if not raw:
        print(f"[news] no source returned anything for {short_name}")
        return {"short_name": short_name, "found": 0, "inserted": 0, "dropped": {}}

    existing = db.news.get_recent_fingerprints(short_name, days=max(days, 7))
    prepared = dedup.prepare(
        raw, short_name, company_name,
        existing=existing,
        aliases=_aliases(stock),
    )

    inserted_ids = db.news.insert_news_many(prepared.rows)

    for news_id, fields in prepared.enrichments.items():
        db.news.update_news(news_id, **fields)

    if score and inserted_ids:
        sentiment_service.score_news_ids(inserted_ids)

    print(f"[news] {short_name}: {len(raw)} found -> {len(inserted_ids)} new "
          f"(dropped {prepared.dropped}, enriched {len(prepared.enrichments)})")

    return {
        "short_name": short_name,
        "found": len(raw),
        "inserted": len(inserted_ids),
        "enriched": len(prepared.enrichments),
        "dropped": prepared.dropped,
    }


def backfill(short_name: str, days: int | None = None) -> dict:
    """Deep pull for a newly followed stock: a month of history by default."""
    days = days or settings.BACKFILL_DAYS
    result = refresh(short_name, days=days)
    images.backfill_images([short_name])
    return result


def refresh_watchlist(days: int = 2) -> dict:
    """Hourly job across every followed stock."""
    watched = db.watchlist.get_symbols()
    if not watched:
        return {"stocks": 0, "inserted": 0}

    total_inserted = 0
    for short_name in watched:
        try:
            total_inserted += refresh(short_name, days=days)["inserted"]
        except Exception as exc:
            print(f"[news] {short_name} failed: {type(exc).__name__}: {exc}")

    images.backfill_images(watched)
    prune()

    print(f"[news] refresh complete: {total_inserted} new articles across {len(watched)} stocks")
    return {"stocks": len(watched), "inserted": total_inserted}


def prune() -> int:
    """Drop articles past the retention window so the DB doesn't grow forever."""
    removed = db.news.delete_older_than(days_ago_iso(settings.NEWS_RETENTION_DAYS))
    if removed:
        print(f"[news] pruned {removed} articles older than {settings.NEWS_RETENTION_DAYS}d")
    return removed

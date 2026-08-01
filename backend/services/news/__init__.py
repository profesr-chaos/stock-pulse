"""News collection: fan out to every source, merge, dedupe, store, score.

Seven fetches across five independent operators, so no single company's outage
or rate limit can take the feed down:

    SEC EDGAR     the filing itself, before anyone reports on it (US, opt-in)
    Finviz        real publisher URLs, dense US coverage
    Yahoo search  thumbnails — the only free image source that costs no request
    Yahoo RSS     summaries
    Nasdaq RSS    wire copy and Nasdaq editorial, real URLs (US)
    Bing News     a second search index, unwrapped to real publisher URLs
    Google News   the broadest reach, and the only one that can backfill a month

Spreading the load this way is also the point: seven polite fetches across five
operators is far kinder to each of them than hammering one supplier, and it
needs no proxy or IP rotation to stay welcome.

GDELT was tried here and removed. Its global index sounds like the obvious way
to cover non-US listings, but the phrase search is too loose to use: `"shell"`
returns awards shows and retirement advice, and the legal suffix that would
make it precise (`"Shell plc"`) is absent from almost all body copy. Add to
that a 20-second TLS handshake and a rate limit that 429s at one request per
five seconds, and it cost more latency per refresh than the six remaining
sources combined while contributing articles the relevance filter then dropped.
Bing already supplies the non-US reach it was added for.

They are queried concurrently and merged, so a source going dark degrades
coverage instead of breaking the refresh. If every source returns nothing, that
genuinely means there is no news, not that a scraper broke — because five
independent things would have had to break at once.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import db
import settings
from normalize import days_ago_iso

from .. import dedup, events, sentiment_service, symbols
from . import bing_news, finviz, google_news, images, nasdaq_news, sec_edgar, yahoo_news

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
    tasks.append(lambda: bing_news.fetch(short_name, company_name, days=days))

    # Finviz, Nasdaq and EDGAR only carry US listings.
    if symbols.is_us_listing(exchange):
        tasks.append(lambda: finviz.fetch(us_ticker))
        tasks.append(lambda: nasdaq_news.fetch(us_ticker))
        tasks.append(lambda: sec_edgar.fetch(us_ticker, company_name))

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


def refresh(short_name: str, days: int = 2, score: bool = True,
            detect_events: bool = True) -> dict:
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

    # Same containment as a source failing in collect(): a dead LLM degrades
    # the refresh to "articles stored, nothing judged", it does not fail it.
    if detect_events and inserted_ids:
        try:
            events.detect(short_name, inserted_ids)
        except Exception as exc:
            print(f"[events] {short_name} failed: {type(exc).__name__}: {exc}")

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
    # A month of history is not "new events" — judging it would spend tokens
    # announcing last month's news. The next hourly refresh takes over.
    result = refresh(short_name, days=days, detect_events=False)
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

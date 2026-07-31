"""The news feed."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import db
from normalize import days_ago_iso, parse_datetime, to_iso
from services import ai_service

from .schemas import AiSummary, NewsArticle, NewsList, parse_symbols, require_symbol, to_news

router = APIRouter(prefix="/news", tags=["News"])


@router.get("", response_model=NewsList)
def feed(
    symbols: str | None = Query(None, description="Comma-separated. Defaults to the watchlist."),
    q: str | None = Query(None, max_length=120, description="Free-text search over headlines."),
    sector: str | None = Query(None, max_length=80, description="Sector or industry name."),
    since: str | None = Query(None, description="ISO 8601 timestamp"),
    days: int = Query(14, ge=1, le=365),
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
    relevance: str | None = Query(None, pattern="^(direct|related)$"),
    sort: str = Query("recent", pattern="^(recent|sentiment|coverage|symbol)$"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Articles for the given symbols, newest first.

    With no `symbols` this returns the whole watchlist's feed, which is what the
    dashboard wants and saves the client assembling the list itself.

    `symbols` is not restricted to the watchlist: the search filter hits the
    whole news table, so a ticker you don't follow still returns whatever has
    been stored for it. `offset` drives the infinite-scroll river — a short page
    means the end of the data, not a transient empty.

    `q`, `sector` and `sort` all resolve in SQL. Doing any of them client-side
    would only ever search or reorder the page already on screen, which reads as
    a broken filter the moment the result set is larger than one page.

    A `sector` naming nothing we hold returns no articles rather than silently
    falling back to the full feed — an empty result is the honest answer to
    "show me biotech" when nothing on the watchlist is biotech.
    """
    # None means "every stock we hold" downstream, which is different from an
    # empty list ("no stocks"), so the two cases cannot be collapsed.
    if symbols:
        wanted = parse_symbols(symbols)
    elif q:
        # A free-text search is explicitly not watchlist-scoped: the user asked
        # for matching articles, not matching articles about stocks they follow.
        wanted = None
    else:
        wanted = db.watchlist.get_symbols()

    if wanted is not None and not wanted:
        return NewsList(results=[])

    if sector:
        wanted = db.stocks.symbols_in_sector(sector, wanted)
        if not wanted:
            return NewsList(results=[])

    if since:
        parsed = parse_datetime(since)
        if not parsed:
            raise HTTPException(status_code=400, detail="`since` must be an ISO 8601 timestamp")
        since_iso = to_iso(parsed)
    else:
        since_iso = days_ago_iso(days)

    rows = db.news.get_news(
        short_names=wanted,
        since=since_iso,
        sentiment=sentiment,
        relevance=relevance,
        query=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return NewsList(results=[to_news(r) for r in rows])


@router.get("/trending", response_model=NewsList)
def trending(
    symbols: str | None = Query(None, description="Comma-separated. Defaults to the watchlist."),
    sector: str | None = Query(None, max_length=80, description="Sector or industry name."),
    days: int = Query(2, ge=1, le=30),
    per_stock: int = Query(3, ge=1, le=10),
    limit: int = Query(12, ge=1, le=60),
):
    """The lead section: articles ordered by their stock's price move.

    "Trending" here means the market moved, not that the article was clicked —
    there is no traffic data to rank by, and the size of a 24h move is the
    honest proxy for what matters today.

    Takes `sector` so the lead narrows with the rest of the page; a filter that
    reordered the feed but left the hero showing an unrelated stock would read
    as the filter having failed.
    """
    wanted = parse_symbols(symbols) if symbols else db.watchlist.get_symbols()
    if not wanted:
        return NewsList(results=[])

    if sector:
        wanted = db.stocks.symbols_in_sector(sector, wanted)
        if not wanted:
            return NewsList(results=[])

    rows = db.news.get_trending(
        short_names=wanted,
        since=days_ago_iso(days),
        per_stock=per_stock,
        limit=limit,
    )
    return NewsList(results=[to_news(r) for r in rows])


@router.get("/latest", response_model=NewsList)
def latest(limit: int = Query(20, ge=1, le=100)):
    """Newest watchlist headlines — the ticker strip on the dashboard."""
    watched = db.watchlist.get_symbols()
    if not watched:
        return NewsList(results=[])
    rows = db.news.get_news(
        short_names=watched, since=days_ago_iso(3), relevance="direct", limit=limit
    )
    return NewsList(results=[to_news(r) for r in rows])


@router.get("/sources")
def sources(symbols: str | None = Query(None), days: int = Query(14, ge=1, le=90)):
    """Article counts per publisher — drives the feed's source filter."""
    wanted = parse_symbols(symbols) if symbols else db.watchlist.get_symbols()
    if not wanted:
        return {"results": []}
    return {"results": db.news.source_breakdown(wanted, since=days_ago_iso(days))}


@router.get("/{news_id}", response_model=NewsArticle)
def article(news_id: int):
    row = db.news.get_news_by_id(news_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return to_news(row)


@router.post("/{news_id}/ai-summary", response_model=AiSummary)
def article_ai_summary(news_id: int):
    """Summarise one article. POST because it can spend tokens."""
    if not ai_service.available():
        raise HTTPException(status_code=503, detail="AI summaries need a DSEEK API key")

    if not db.news.get_news_by_id(news_id):
        raise HTTPException(status_code=404, detail="Article not found")

    result = ai_service.summarise_article(news_id)
    if not result:
        raise HTTPException(status_code=502, detail="Could not generate a summary")
    return AiSummary(id=result["id"], ai_summary=result["ai_summary"], cached=result["cached"])


@router.post("/stock/{symbol}/ai-summary", response_model=AiSummary)
def stock_ai_summary(symbol: str, days: int = Query(7, ge=1, le=30)):
    """Digest of a stock's recent coverage. Cached for 24h, or until new news."""
    symbol = require_symbol(symbol)
    if not ai_service.available():
        raise HTTPException(status_code=503, detail="AI summaries need a DSEEK API key")

    result = ai_service.summarise_stock(symbol, days=days)
    if not result:
        raise HTTPException(status_code=404, detail=f"No recent news to summarise for {symbol}")
    return AiSummary(
        symbol=result["symbol"], ai_summary=result["ai_summary"], cached=result["cached"]
    )

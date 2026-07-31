"""Aggregates for the dashboard panels.

These replace the hard-coded mock arrays the frontend was shipping (a fake
"NVDA 1243 mentions" list). All computed from stored articles and quotes, so
they are only ever as good as the watchlist's coverage — which is the honest
behaviour for a personal tool with no cross-user data to draw on.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

import db
from normalize import days_ago_iso

from .schemas import Mover, TrendingStock

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("/trending")
def trending(days: int = Query(3, ge=1, le=30), limit: int = Query(6, ge=1, le=20)):
    """Most-covered, most-positive and sharpest-negative stocks."""
    symbols = db.watchlist.get_symbols()
    if not symbols:
        return {"mostDiscussed": [], "mostPositive": [], "negativeSpikes": []}

    counts = db.news.count_by_stock(since=days_ago_iso(days), short_names=symbols)
    stocks = {s["short_name"]: s for s in db.stocks.get_stocks(symbols)}
    deltas = {d["short_name"]: d for d in db.sentiment.get_deltas(symbols, window_days=days)}

    def build(row: dict) -> TrendingStock:
        stock = stocks.get(row["short_name"], {})
        return TrendingStock(
            symbol=row["short_name"],
            name=stock.get("name"),
            articleCount=row["article_count"],
            avgSentiment=_round(row.get("avg_sentiment")),
            changePercent=stock.get("price_change_percent"),
        )

    ranked = [build(r) for r in counts]
    scored = [s for s in ranked if s.avgSentiment is not None]

    spikes = []
    for symbol, delta in deltas.items():
        recent, baseline = delta.get("recent_sentiment"), delta.get("baseline_sentiment")
        if recent is None:
            continue
        # A stock that just turned negative is news; one that is always
        # negative is not.
        drop = recent - baseline if baseline is not None else recent
        if recent < -0.05 and drop < 0:
            stock = stocks.get(symbol, {})
            spikes.append(TrendingStock(
                symbol=symbol,
                name=stock.get("name"),
                articleCount=int(delta.get("recent_articles") or 0),
                avgSentiment=_round(recent),
                changePercent=stock.get("price_change_percent"),
            ))
    spikes.sort(key=lambda s: s.avgSentiment or 0)

    return {
        "mostDiscussed": ranked[:limit],
        "mostPositive": sorted(scored, key=lambda s: -(s.avgSentiment or 0))[:limit],
        "negativeSpikes": spikes[:limit],
    }


@router.get("/movers")
def movers(days: int = Query(3, ge=1, le=30), limit: int = Query(8, ge=1, le=30)):
    """Watchlist stocks by absolute price move, with their sentiment shift."""
    symbols = db.watchlist.get_symbols()
    if not symbols:
        return {"results": []}

    stocks = db.stocks.get_stocks(symbols)
    counts = {c["short_name"]: c for c in db.news.count_by_stock(
        since=days_ago_iso(days), short_names=symbols)}
    deltas = {d["short_name"]: d for d in db.sentiment.get_deltas(symbols, window_days=days)}

    results = []
    for stock in stocks:
        symbol = stock["short_name"]
        delta = deltas.get(symbol) or {}
        recent, baseline = delta.get("recent_sentiment"), delta.get("baseline_sentiment")
        results.append(Mover(
            symbol=symbol,
            name=stock.get("name"),
            price=stock.get("price"),
            currencyCode=stock.get("quote_currency") or stock.get("currency_code"),
            changePercent=stock.get("price_change_percent"),
            sentiment=_round(recent if recent is not None
                             else (counts.get(symbol) or {}).get("avg_sentiment")),
            sentimentDelta=_round(recent - baseline) if recent is not None and baseline is not None else None,
            articleCount=int((counts.get(symbol) or {}).get("article_count") or 0),
        ))

    results.sort(key=lambda m: -abs(m.changePercent or 0))
    return {"results": results[:limit]}


@router.get("/sentiment/{symbol}")
def sentiment_history(symbol: str, days: int = Query(30, ge=1, le=180)):
    """Daily sentiment series for one stock."""
    from .schemas import require_symbol
    return {"results": db.sentiment.get_history(require_symbol(symbol), days=days)}


def _round(value) -> float | None:
    return round(value, 3) if isinstance(value, (int, float)) else None

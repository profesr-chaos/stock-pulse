"""Instrument search, quotes and price history."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

import db
import settings
from normalize import clean_symbol, now_utc, parse_datetime
from services import prices, symbols

from .schemas import (
    PricePoint,
    PriceSeries,
    Sector,
    SectorList,
    Stock,
    StockList,
    parse_symbols,
    require_symbol,
    to_stock,
)

router = APIRouter(prefix="/stocks", tags=["Stocks"])

# Stored hits and Yahoo hits are concatenated, so cap the total. Matches the
# default limit db.stocks.search_stocks applies on its own.
_SEARCH_LIMIT = 25


@router.get("/search", response_model=StockList)
def search(q: str = Query(..., min_length=1, max_length=64)):
    """Stored instruments first, then Yahoo for anything we have never seen.

    The trigger is a missing *exact ticker*, not an empty result. An empty
    result is rare and a bad signal: the catalogue is full of wrappers carrying
    the underlying's name, so deleting AMZN still leaves six rows matching
    "AMZN" — `3SAM` (Leverage Shares -3x Short Amazon) among them. Falling back
    only on a blank would answer that search with a triple-short ETP and never
    consult Yahoo for the company itself.

    Nothing is written here. A looked-up instrument becomes a `stocks` row only
    when it is actually followed, which keeps the catalogue free of every
    half-typed query and keeps search a pure read.
    """
    query = q.strip()
    results = db.stocks.search_stocks(query)

    if not any(r["short_name"] == clean_symbol(query) for r in results):
        # Skip anything already stored, by short_name *and* by resolved symbol:
        # Rocket Lab is stored as `6RJ0` resolved to `RKLB`, and offering both
        # would let someone follow the same company twice.
        stored = {r["short_name"] for r in results}
        stored |= {r["yahoo_symbol"] for r in results if r.get("yahoo_symbol")}
        found = [r for r in symbols.lookup(query) if r["short_name"] not in stored]
        # Yahoo's relevance ordering goes first: it puts the underlying above
        # the derivatives, which is the whole point of asking it.
        results = found + results

    return StockList(results=[to_stock(s) for s in results[:_SEARCH_LIMIT]])


@router.get("/sectors", response_model=SectorList)
def sectors(watchlist_only: bool = Query(True)):
    """Sectors available to filter by, most-held first.

    Scoped to the watchlist by default: the catalogue holds 15k instruments but
    only followed stocks have news, so offering the full taxonomy would be a
    menu of mostly-empty filters. Anything unclassified — funds and indices,
    which Yahoo does not label — is simply absent.
    """
    symbols = db.watchlist.get_symbols() if watchlist_only else None
    return SectorList(results=[
        Sector(sector=r["sector"], level=r["level"],
               group=r.get("group_name"), stockCount=r["stock_count"])
        for r in db.stocks.get_sectors(symbols)
    ])


@router.get("/popular", response_model=StockList)
def popular(limit: int = Query(10, ge=1, le=50)):
    """The watchlist first, topped up with the most-covered stocks.

    With no notion of other users there is no "popular" to compute, so this is
    "what you follow" plus whatever we have the most news on.
    """
    watched = db.watchlist.get_watchlist()
    results = [to_stock(s) for s in watched]

    if len(results) < limit:
        seen = {s.symbol for s in results}
        busiest = db.news.count_by_stock(since=_week_ago(), short_names=None)
        fill = [row["short_name"] for row in busiest if row["short_name"] not in seen]
        for stock in db.stocks.get_stocks(fill[: limit - len(results)]):
            results.append(to_stock(stock))

    return StockList(results=results[:limit])


def _week_ago() -> str:
    from normalize import days_ago_iso
    return days_ago_iso(7)


@router.get("/quotes", response_model=StockList)
def quotes(background: BackgroundTasks, symbols: str = Query(..., alias="symbols")):
    """Latest quotes, served from the DB.

    A symbol with no price yet is fetched inline so the UI never shows blanks
    for a stock that was just added; a merely stale one is served immediately
    and refreshed in the background. Reads stay fast either way.
    """
    wanted = parse_symbols(symbols)
    stored = {s["short_name"]: s for s in db.stocks.get_stocks(wanted)}

    stale: list[str] = []
    results: list[Stock] = []

    for symbol in wanted:
        row = stored.get(symbol)
        if row is None:
            results.append(Stock(symbol=symbol))
            continue

        if row.get("price") is None:
            fetched = prices.refresh_stock(symbol)
            if fetched:
                row = db.stocks.get_stock(symbol) or row
        elif _is_stale(row.get("price_updated_at")):
            stale.append(symbol)

        results.append(to_stock(row))

    for symbol in stale:
        background.add_task(prices.refresh_stock, symbol)

    return StockList(results=results)


def _is_stale(updated_at: str | None) -> bool:
    if not updated_at:
        return True
    when = parse_datetime(updated_at)
    if not when:
        return True
    return (now_utc() - when).total_seconds() > settings.QUOTE_STALE_MINUTES * 60


@router.get("/{symbol}", response_model=Stock)
def detail(symbol: str):
    row = db.stocks.get_stock(require_symbol(symbol))
    if not row:
        raise HTTPException(status_code=404, detail="Stock not found")
    return to_stock(row)


@router.get("/{symbol}/prices", response_model=PriceSeries)
def price_history(symbol: str, days: int = Query(30, ge=1, le=365)):
    """Daily closes plus intraday snapshots for days without a close yet."""
    symbol = require_symbol(symbol)
    row = db.stocks.get_stock(symbol)
    if not row:
        raise HTTPException(status_code=404, detail="Stock not found")

    series = prices.get_series(symbol, days=days)
    row = db.stocks.get_stock(symbol) or row      # get_series may have refreshed

    return PriceSeries(
        symbol=symbol,
        currency=row.get("quote_currency") or row.get("currency_code"),
        price=row.get("price"),
        change=row.get("price_change"),
        changePercent=row.get("price_change_percent"),
        points=[PricePoint(ts=p["ts"], close=p["close"]) for p in series],
    )

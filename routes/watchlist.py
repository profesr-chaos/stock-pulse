"""The watchlist. No auth — one user, one list."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

import db
import jobs

from .schemas import Ok, StockList, require_symbol, to_stock

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])

MAX_WATCHLIST = 100


class AddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)


class ReorderRequest(BaseModel):
    symbols: list[str] = Field(..., max_length=MAX_WATCHLIST)


@router.get("", response_model=StockList)
def get_watchlist():
    return StockList(results=[to_stock(s) for s in db.watchlist.get_watchlist()])


@router.post("", response_model=Ok, status_code=201)
def add(body: AddRequest, background: BackgroundTasks):
    """Follow a stock and immediately start pulling its history.

    The backfill (a month of prices and news) runs in the background so the
    request returns straight away, and the feed fills in rather than sitting
    empty until the next hourly refresh.
    """
    symbol = require_symbol(body.symbol)

    if not db.stocks.get_stock(symbol):
        raise HTTPException(status_code=404, detail=f"{symbol} is not in the instrument catalogue")

    if len(db.watchlist.get_symbols()) >= MAX_WATCHLIST:
        raise HTTPException(status_code=400, detail=f"Watchlist is limited to {MAX_WATCHLIST} stocks")

    if not db.watchlist.add(symbol):
        raise HTTPException(status_code=409, detail=f"{symbol} is already on the watchlist")

    background.add_task(jobs.backfill_stock, symbol)
    return Ok()


@router.delete("/{symbol}", response_model=Ok)
def remove(symbol: str):
    """Unfollow. Stored news and prices are left alone, so re-adding is instant."""
    if not db.watchlist.remove(require_symbol(symbol)):
        raise HTTPException(status_code=404, detail="Not on the watchlist")
    return Ok()


@router.put("/reorder", response_model=Ok)
def reorder(body: ReorderRequest):
    db.watchlist.reorder([require_symbol(s) for s in body.symbols])
    return Ok()


@router.post("/{symbol}/refresh", response_model=Ok, status_code=202)
def refresh_one(symbol: str, background: BackgroundTasks):
    """Force a re-scrape of one stock."""
    symbol = require_symbol(symbol)
    if not db.watchlist.is_following(symbol):
        raise HTTPException(status_code=404, detail="Not on the watchlist")
    background.add_task(jobs.backfill_stock, symbol)
    return Ok()

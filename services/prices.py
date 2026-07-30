"""Prices, free of charge, with a real fallback chain.

    1. Yahoo chart v8  — quote *and* daily history in one request, two hosts
    2. CNBC quote API  — independent host, no key, global coverage

Both are hit through the adaptive scraper, so a throttled Yahoo drops its rate
and CNBC picks up the slack rather than the refresh failing.

History comes from Yahoo only. If Yahoo is unavailable the quote still updates
from CNBC and the stored history simply stops extending — degraded, not broken.

Everything is stored in *major* currency units: LSE quotes arrive in pence and
Tel Aviv in agorot, and a chart that silently mixes 3323.5 with 33.235 is worse
than no chart.
"""
from __future__ import annotations

import json
import re

import db
from normalize import days_ago_iso, now_utc, to_iso

from . import symbols, yahoo
from .http_client import scraper

_CNBC_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"

# Yahoo exchange suffix → CNBC country code, for the cases where CNBC will not
# take the Yahoo symbol as-is.
_CNBC_SUFFIX = {
    "L": "GB", "DE": "DE", "F": "DE", "PA": "FR", "AS": "NL", "BR": "BE",
    "MI": "IT", "MC": "ES", "SW": "CH", "ST": "SE", "CO": "DK", "OL": "NO",
    "HE": "FI", "VI": "AT", "LS": "PT", "TO": "CA", "HK": "HK", "T": "JP",
    "AX": "AU", "NZ": "NZ",
}

_NUMBER = re.compile(r"-?[\d,]+\.?\d*")


def _to_float(value) -> float | None:
    """CNBC returns display strings: '3,323.50', '-0.56%', 'UNCH'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER.search(str(value).replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


# ── Sources ──────────────────────────────────────────────────────────────

def from_yahoo(yahoo_symbol: str, range_: str = "1mo") -> dict | None:
    chart = yahoo.chart(yahoo_symbol, range_=range_, interval="1d")
    if not chart or chart.get("price") is None:
        return None
    return {**chart, "source": "yahoo"}


def from_cnbc(yahoo_symbol: str) -> dict | None:
    """CNBC accepts Yahoo-style symbols (`SHEL.L`) as well as its own
    (`SHEL-GB`), so try the symbol we already have before translating."""
    for candidate in _cnbc_candidates(yahoo_symbol):
        parsed = _cnbc_quote(candidate)
        if parsed:
            return parsed
    return None


def _cnbc_candidates(yahoo_symbol: str) -> list[str]:
    candidates = [yahoo_symbol]
    if "." in yahoo_symbol:
        base, suffix = yahoo_symbol.rsplit(".", 1)
        country = _CNBC_SUFFIX.get(suffix.upper())
        if country:
            candidates.append(f"{base}-{country}")
    return candidates


def _cnbc_quote(symbol: str) -> dict | None:
    raw = scraper.get(
        _CNBC_URL,
        params={
            "symbols": symbol, "requestMethod": "itv", "noform": "1",
            "partnerId": "2", "fund": "1", "output": "json",
        },
        headers={"Accept": "application/json, text/plain, */*"},
    )
    if not raw or not raw.ok:
        return None
    try:
        quotes = (json.loads(raw.text).get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
    except (ValueError, AttributeError):
        return None
    if isinstance(quotes, dict):
        quotes = [quotes]
    if not quotes:
        return None

    quote = quotes[0]
    price = _to_float(quote.get("last"))
    if not price:
        return None

    currency, divisor = yahoo.normalise_currency(quote.get("currencyCode"))
    previous = _to_float(quote.get("previous_day_closing"))
    change = _to_float(quote.get("change"))
    if change is None and previous:
        change = price - previous

    return {
        "symbol": quote.get("symbol"),
        "exchange": quote.get("exchange"),
        "currency": currency,
        "price": round(price / divisor, 6),
        "previous_close": round(previous / divisor, 6) if previous else None,
        "change": round(change / divisor, 6) if change is not None else None,
        "change_percent": _to_float(quote.get("change_pct")),
        "points": [],
        "source": "cnbc",
    }


def get_quote(yahoo_symbol: str, range_: str = "1mo") -> dict | None:
    """Walk the chain. None only if every source failed."""
    return from_yahoo(yahoo_symbol, range_=range_) or from_cnbc(yahoo_symbol)


# ── Refresh (writes to the DB) ───────────────────────────────────────────

def ensure_resolved(stock: dict) -> str | None:
    """The Yahoo symbol for a stock, resolving and caching it on first use."""
    if stock.get("yahoo_symbol"):
        return stock["yahoo_symbol"]

    resolved = symbols.resolve(stock["short_name"], stock.get("name"))
    if not resolved:
        return None
    db.stocks.set_resolution(
        stock["short_name"], resolved["symbol"],
        resolved.get("exchange"), resolved.get("currency"),
    )
    print(f"[prices] resolved {stock['short_name']} -> "
          f"{resolved['symbol']} ({resolved.get('exchange')})")
    return resolved["symbol"]


def refresh_stock(short_name: str, range_: str = "5d") -> dict | None:
    """Update one stock's quote and history. `range_='1mo'` for a backfill."""
    stock = db.stocks.get_stock(short_name)
    if not stock:
        print(f"[prices] {short_name} not in catalogue")
        return None

    yahoo_symbol = ensure_resolved(stock)
    if not yahoo_symbol:
        return None

    quote = get_quote(yahoo_symbol, range_=range_)
    if not quote:
        print(f"[prices] all sources failed for {short_name} ({yahoo_symbol})")
        return None

    _store(short_name, quote)
    return quote


def _store(short_name: str, quote: dict) -> None:
    if quote.get("points"):
        # Daily bars are stamped at midnight UTC so one trading day is one row
        # regardless of which session time the exchange reports.
        db.prices.upsert_points(
            short_name,
            [(ts[:10] + "T00:00:00Z", close) for ts, close in quote["points"]],
            interval="1d",
        )

    _store_snapshot(short_name, quote["price"])

    db.stocks.bulk_set_quotes([{
        "short_name": short_name,
        "price": quote["price"],
        "change": quote.get("change"),
        "change_percent": quote.get("change_percent"),
        "currency": quote.get("currency"),
    }])


def _store_snapshot(short_name: str, price: float) -> None:
    """One point per hour, and only when the price actually moved.

    Skipping unchanged prices means an overnight or weekend refresh doesn't
    stamp out a flat line of duplicate points — cheaper than tracking the
    opening hours of forty exchanges just to decide whether to write a row.
    """
    latest = db.prices.latest(short_name)
    if latest and abs(latest["close"] - price) < 1e-9:
        return
    stamp = to_iso(now_utc().replace(minute=0, second=0, microsecond=0))
    db.prices.upsert_points(short_name, [(stamp, price)], interval="snap")


def refresh_watchlist(range_: str = "5d") -> dict:
    """Hourly job: refresh every followed stock."""
    watched = db.watchlist.get_symbols()
    if not watched:
        return {"updated": [], "failed": []}

    updated, failed = [], []
    for short_name in watched:
        try:
            if refresh_stock(short_name, range_=range_):
                updated.append(short_name)
            else:
                failed.append(short_name)
        except Exception as exc:                      # one bad symbol must not
            print(f"[prices] {short_name} errored: {exc}")   # stall the rest
            failed.append(short_name)

    print(f"[prices] {len(updated)} updated, {len(failed)} failed {failed if failed else ''}")
    return {"updated": updated, "failed": failed}


def get_series(short_name: str, days: int = 30) -> list[dict]:
    """Chart data, backfilling from the network if the DB has nothing yet."""
    since = days_ago_iso(days)
    series = db.prices.get_series(short_name, since)
    if not series:
        refresh_stock(short_name, range_="1mo")
        series = db.prices.get_series(short_name, since)
    return series

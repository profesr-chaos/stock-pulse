"""Prices, free of charge, with a real fallback chain.

    1. Yahoo chart v8  — quote *and* daily history in one request, two hosts
    2. Nasdaq quote    — US listings, real-time during the session, own host
    3. CNBC quote API  — independent host, no key, global coverage

Three different operators, hit through the adaptive scraper, so a throttled
Yahoo drops its rate and the next source picks up the slack rather than the
refresh failing. Diversifying across suppliers is what keeps this polite:
nobody is being leaned on hard enough to notice, and no proxy or IP rotation
is needed to stay welcome.

History comes from Yahoo only. If Yahoo is unavailable the quote still updates
from a fallback and the stored history simply stops extending — degraded, not
broken.

Everything is stored in *major* currency units: LSE quotes arrive in pence and
Tel Aviv in agorot, and a chart that silently mixes 3323.5 with 33.235 is worse
than no chart.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

import db
import settings
from normalize import days_ago_iso, now_utc, to_iso

from . import symbols, yahoo
from .http_client import scraper

_CNBC_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
_NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/info"

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


def from_nasdaq(yahoo_symbol: str) -> dict | None:
    """US listings only, and deliberately so.

    A suffixed symbol names a foreign line — `SHEL.L` is the London ordinary,
    not the New York ADR — and Nasdaq would happily answer with the ADR at a
    different price in a different currency. Returning None for anything
    suffixed is what stops that silent mismatch.
    """
    if "." in yahoo_symbol or "^" in yahoo_symbol:
        return None

    data = scraper.get_json(
        _NASDAQ_URL.format(symbol=yahoo_symbol.upper()),
        params={"assetclass": "stocks"},
        headers={"Accept": "application/json"},
    )
    if not isinstance(data, dict):
        return None
    quote = data.get("data")
    if not isinstance(quote, dict):
        return None

    session = _nasdaq_session(quote)
    price = _to_float(session.get("lastSalePrice"))
    if not price:
        return None

    change = _to_float(session.get("netChange"))
    return {
        "symbol": quote.get("symbol") or yahoo_symbol,
        "exchange": quote.get("exchange"),
        "currency": "USD",
        "price": round(price, 6),
        "previous_close": round(price - change, 6) if change is not None else None,
        "change": change,
        "change_percent": _to_float(session.get("percentageChange")),
        "points": [],
        "source": "nasdaq",
    }


def _nasdaq_session(quote: dict) -> dict:
    """The regular-session block, whichever of the two it happens to be.

    Nasdaq splits a quote in two: `primaryData` is whatever is trading right
    now, and once the bell goes that becomes the extended-hours print while
    `secondaryData` holds the regular close. Taking primaryData blindly would
    store an after-hours price as the day's close and put a point on the chart
    that no other source agrees with, so the regular session wins whenever it
    is present.
    """
    secondary = quote.get("secondaryData")
    if isinstance(secondary, dict) and secondary.get("lastSalePrice"):
        return secondary
    primary = quote.get("primaryData")
    return primary if isinstance(primary, dict) else {}


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
    return (from_yahoo(yahoo_symbol, range_=range_)
            or from_nasdaq(yahoo_symbol)
            or from_cnbc(yahoo_symbol))


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
    _store_classification(stock["short_name"], resolved)
    print(f"[prices] resolved {stock['short_name']} -> "
          f"{resolved['symbol']} ({resolved.get('exchange')})")
    return resolved["symbol"]


def _store_classification(short_name: str, resolved: dict) -> None:
    """Persist Yahoo's sector/industry, when it gave us one."""
    fields = {k: resolved.get(k) for k in ("sector", "industry") if resolved.get(k)}
    if fields:
        db.stocks.update_stock(short_name, **fields)


def ensure_classified(stock: dict) -> bool:
    """Fill in a missing sector for an already-resolved stock.

    Resolution caches `yahoo_symbol` on the row, so every stock followed before
    the sector column existed short-circuits ensure_resolved() and would never
    pick one up. This re-runs just the search half — `validate=False` skips the
    chart call, since we already trust the symbol and only want its label.

    ETFs and indices are genuinely unclassified by Yahoo, so a stock that comes
    back empty is not retried into a loop: it is simply left NULL and filtered
    out of the sector list.
    """
    if stock.get("sector") or not stock.get("yahoo_symbol"):
        return False

    resolved = symbols.resolve(stock["short_name"], stock.get("name"), validate=False)
    if not resolved or not resolved.get("sector"):
        return False

    _store_classification(stock["short_name"], resolved)
    print(f"[prices] classified {stock['short_name']} -> {resolved['sector']}"
          f" / {resolved.get('industry')}")
    return True


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
    """Scheduled job: refresh every followed stock, concurrently.

    Sequentially this took one full chain-walk per stock, so a twenty-stock
    watchlist was minutes behind the market by the time it finished — the
    opposite of the point. The per-host token buckets in the scraper still
    pace each source, so this parallelises across stocks without hitting any
    one source harder than the sequential version did.
    """
    watched = db.watchlist.get_symbols()
    if not watched:
        return {"updated": [], "failed": []}

    def refresh_one(short_name: str) -> bool:
        try:
            ok = bool(refresh_stock(short_name, range_=range_))
            # After the quote, so a classification lookup can never cost the
            # price its refresh. Only ever does work once per stock.
            stock = db.stocks.get_stock(short_name)
            if stock:
                ensure_classified(stock)
            return ok
        except Exception as exc:                      # one bad symbol must not
            print(f"[prices] {short_name} errored: {exc}")   # stall the rest
            return False

    workers = min(settings.SCRAPE_CONCURRENCY, len(watched))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prices") as pool:
        outcomes = list(pool.map(refresh_one, watched))

    updated = [s for s, ok in zip(watched, outcomes) if ok]
    failed = [s for s, ok in zip(watched, outcomes) if not ok]

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

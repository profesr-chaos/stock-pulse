"""Raw Yahoo Finance endpoints. Parsing only — no DB, no business rules.

These are the public JSON endpoints a browser hits, so no key and no crumb
dance. The chart endpoint is the workhorse: one call returns the live quote
*and* the historical series, which is why there is no separate bulk-quote path
to keep working. Fewer code paths, more data per request.
"""
from __future__ import annotations

from normalize import to_iso

from .http_client import Fetched, scraper

# Two hostnames serve identical data. When one starts throttling, the other is
# usually still happy — a free extra token bucket.
_CHART_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]

_SEARCH_HOSTS = [
    "https://query2.finance.yahoo.com",
    "https://query1.finance.yahoo.com",
]

# Quotes come back in the exchange's minor unit for a few venues; divide to get
# major units so the number next to a "£" is actually pounds.
_MINOR_UNIT_DIVISORS = {
    "GBP": 1.0, "GBp": 100.0, "GBX": 100.0,   # LSE quotes in pence
    "ZAC": 100.0, "ZAR": 1.0,                  # Johannesburg in cents
    "ILA": 100.0, "ILS": 1.0,                  # Tel Aviv in agorot
}


def normalise_currency(currency: str | None) -> tuple[str, float]:
    """('GBp', 100.0) → quotes are in pence, divide by 100 to get GBP."""
    if not currency:
        return "", 1.0
    divisor = _MINOR_UNIT_DIVISORS.get(currency)
    if divisor is None:
        # Unknown code: pass through untouched rather than guess.
        return currency.upper(), 1.0
    major = {"GBp": "GBP", "GBX": "GBP", "ZAC": "ZAR", "ILA": "ILS"}.get(currency, currency)
    return major.upper(), divisor


def _api_headers(referer: str = "https://finance.yahoo.com/") -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Origin": "https://finance.yahoo.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }


def _try_hosts(hosts: list[str], path: str, params: dict, cache: bool = True) -> dict | None:
    """First host that answers wins; the rest are free retries on a fresh bucket."""
    for host in hosts:
        data = scraper.get_json(host + path, params=params, headers=_api_headers(), cache=cache)
        if isinstance(data, dict):
            return data
    return None


# ── Chart: quote + history in one request ────────────────────────────────

def chart(symbol: str, range_: str = "1mo", interval: str = "1d") -> dict | None:
    """Parsed chart payload, or None.

    Returns:
        {"symbol", "exchange", "currency", "price", "previous_close",
         "change", "change_percent", "points": [(iso_ts, close)]}
    """
    data = _try_hosts(
        _CHART_HOSTS,
        f"/v8/finance/chart/{symbol}",
        {"range": range_, "interval": interval, "includePrePost": "false", "events": "div,split"},
        cache=(interval != "1m"),
    )
    if not data:
        return None
    return parse_chart(data)


def parse_chart(data: dict) -> dict | None:
    """Split out so it can be tested against a captured payload."""
    try:
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            return None
        node = result[0]
        meta = node.get("meta") or {}
    except (AttributeError, TypeError):
        return None

    currency, divisor = normalise_currency(meta.get("currency"))

    stamps = node.get("timestamp") or []
    quote_blocks = ((node.get("indicators") or {}).get("quote") or [{}])
    closes = (quote_blocks[0] or {}).get("close") or []

    points: list[tuple[str, float]] = []
    for ts, close in zip(stamps, closes):
        if close is None or ts is None:
            continue          # market holiday / missing bar
        points.append((_iso_from_epoch(ts), round(close / divisor, 6)))

    price = meta.get("regularMarketPrice")
    if price is None and points:
        price = points[-1][1] * divisor
    if price is None:
        return None
    price = price / divisor

    # previousClose is the reliable field; chartPreviousClose is the close
    # before the window; the prior bar is the last resort.
    previous = meta.get("previousClose")
    if previous is None and len(points) >= 2:
        previous = points[-2][1] * divisor
    if previous is None:
        previous = meta.get("chartPreviousClose")
    previous = (previous / divisor) if previous else None

    change = round(price - previous, 6) if previous else None
    change_percent = (
        round((change / previous) * 100, 3) if previous and change is not None else None
    )

    return {
        "symbol": meta.get("symbol"),
        "exchange": meta.get("exchangeName"),
        "exchange_name": meta.get("fullExchangeName"),
        "instrument_type": meta.get("instrumentType"),
        "currency": currency,
        "price": round(price, 6),
        "previous_close": round(previous, 6) if previous else None,
        "change": change,
        "change_percent": change_percent,
        "points": points,
    }


def _iso_from_epoch(seconds: int) -> str:
    from datetime import datetime, timezone
    return to_iso(datetime.fromtimestamp(seconds, timezone.utc))


# ── Search: symbol resolution + a news side-channel ──────────────────────

def search(query: str, quotes: int = 10, news: int = 0) -> dict:
    """Yahoo's autocomplete. Doubles as a news source with real thumbnails."""
    data = _try_hosts(
        _SEARCH_HOSTS,
        "/v1/finance/search",
        {
            "q": query,
            "quotesCount": quotes,
            "newsCount": news,
            "listsCount": 0,
            "enableFuzzyQuery": "false",
            "quotesQueryId": "tss_match_phrase_query",
            "newsQueryId": "news_cie_vespa",
        },
    )
    if not data:
        return {"quotes": [], "news": []}
    return {"quotes": data.get("quotes") or [], "news": data.get("news") or []}


def rss_headlines(symbol: str) -> Fetched | None:
    """Yahoo's per-ticker RSS. Older endpoint, still live, carries summaries."""
    return scraper.get(
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
        params={"s": symbol, "region": "US", "lang": "en-US"},
        headers={"Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"},
    )

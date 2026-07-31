"""Pick one canonical listing per instrument, so prices are comparable.

The same company trades on many venues in many currencies. The catalogue we
inherit from Trading212 is not a reliable guide to which one — it reports TSLA
as an EUR instrument — so listings are resolved against Yahoo and ranked by
exchange, preferring the deepest, most-quoted market:

    US primary  →  London  →  XETRA  →  rest of Europe  →  Canada
                →  German regional  →  depositary receipts  →  everything else

Resolution happens once per stock and is cached on the row.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from normalize import clean_symbol

from . import yahoo

# Lower rank wins. Codes are Yahoo's `exchange` field.
_EXCHANGE_RANK: dict[str, int] = {
    # US primary listings — deepest liquidity, and the currency everything else
    # gets compared against.
    "NMS": 0, "NYQ": 0, "NGM": 0, "NCM": 0, "NAS": 0, "NYS": 0,
    "ASE": 1, "PCX": 1, "BTS": 1, "NEO": 1,
    # London
    "LSE": 2,
    # Frankfurt XETRA — the German venue with real volume
    "GER": 3,
    # Rest of western Europe
    "AMS": 4, "PAR": 4, "MIL": 4, "EBS": 4, "BRU": 4, "LIS": 4, "MCE": 4,
    "STO": 4, "CPH": 4, "OSL": 4, "HEL": 4, "VIE": 4, "ISE": 4,
    # Canada
    "TOR": 5, "VAN": 6, "CNQ": 6,
    # German regional exchanges: same company, a fraction of the volume
    "FRA": 7, "STU": 7, "MUN": 7, "BER": 7, "DUS": 7, "HAM": 7, "HAN": 7, "GETTEX": 7,
    # Depositary receipts / international order book
    "IOB": 8,
    # Asia-Pacific and the rest
    "TYO": 9, "JPX": 9, "HKG": 9, "SHH": 9, "SHZ": 9, "KSC": 9, "KOE": 9,
    "TAI": 9, "ASX": 9, "NSI": 9, "BSE": 9, "SES": 9, "NZE": 9,
    "SAO": 10, "MEX": 10, "JNB": 10, "TLV": 10, "IST": 10, "WSE": 10,
}
_UNKNOWN_EXCHANGE_RANK = 12

_US_EXCHANGES = frozenset({"NMS", "NYQ", "NGM", "NCM", "NAS", "NYS", "ASE", "PCX", "BTS"})

# Instrument kinds we can price and find news for.
_ALLOWED_TYPES = frozenset({"EQUITY", "ETF", "MUTUALFUND", "INDEX"})

# Below this the Yahoo hit is probably a different company that happens to
# share a ticker.
_NAME_MATCH_FLOOR = 55

# Leveraged/inverse wrappers are not the underlying. If our catalogue name has
# none of these but a candidate does, it's the wrong instrument.
_DERIVATIVE_MARKERS = (
    "leverage shares", "leveraged", " -1x", " -2x", " -3x", " 1x ", " 2x ", " 3x ",
    "inverse", "short ", "etp", "etn", "certificate", "warrant", "turbo",
    "call option", "put option", "options ",
)


def exchange_rank(exchange: str | None) -> int:
    if not exchange:
        return _UNKNOWN_EXCHANGE_RANK
    return _EXCHANGE_RANK.get(exchange.upper(), _UNKNOWN_EXCHANGE_RANK)


def is_us_listing(exchange: str | None) -> bool:
    return bool(exchange) and exchange.upper() in _US_EXCHANGES


def _looks_derivative(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(marker in lowered for marker in _DERIVATIVE_MARKERS)


# Every ticker on the LSE International Board starts with a digit (0NCA.L is
# IVU Traffic Technologies' London line). Yahoo labels these plain "LSE", but
# they are cross-listings of a foreign primary and barely trade — IVU's London
# line had 15 daily bars in a month where its XETRA line had a full set. Rank
# them below the real European venues.
_INTL_BOARD_PENALTY = 6


def _ranked(symbol: str, exchange: str | None) -> int:
    rank = exchange_rank(exchange)
    if (exchange or "").upper() == "LSE" and symbol[:1].isdigit():
        rank += _INTL_BOARD_PENALTY
    return rank


def name_score(catalogue_name: str, candidate: dict) -> int:
    """How confident we are that a Yahoo hit is the same company."""
    names = [candidate.get("longname"), candidate.get("shortname")]
    return max(
        (fuzz.token_set_ratio(catalogue_name.lower(), n.lower()) for n in names if n),
        default=0,
    )


def score_candidates(short_name: str, catalogue_name: str, candidates: list[dict]) -> list[dict]:
    """Filter to plausible listings of this company and rank them.

    Pure function: the whole exchange hierarchy is testable without a network.
    """
    symbol_upper = clean_symbol(short_name)
    catalogue_is_derivative = _looks_derivative(catalogue_name)
    scored = []

    for candidate in candidates:
        symbol = candidate.get("symbol")
        if not symbol or (candidate.get("quoteType") or "").upper() not in _ALLOWED_TYPES:
            continue

        matched_name = name_score(catalogue_name, candidate)
        exact_symbol = symbol.upper() == symbol_upper

        # A matching *base* symbol (SHEL.L for SHEL) is not on its own enough:
        # tickers collide across exchanges, and APP.AX is Appen Limited, not
        # AppLovin. The name has to agree, or the symbol has to match exactly.
        if not (matched_name >= _NAME_MATCH_FLOOR or exact_symbol):
            continue

        candidate_text = f"{candidate.get('longname') or ''} {candidate.get('shortname') or ''}"
        if _looks_derivative(candidate_text) != catalogue_is_derivative:
            continue

        scored.append({
            "symbol": symbol,
            "exchange": candidate.get("exchange"),
            "name": candidate.get("longname") or candidate.get("shortname") or catalogue_name,
            "quote_type": (candidate.get("quoteType") or "").upper(),
            # Yahoo's search payload already carries the classification, so the
            # sector comes free with resolution — no second request, and no
            # quoteSummary call (that one now demands a crumb). Funds and
            # indices return null for both; only equities are classified.
            "sector": candidate.get("sector"),
            "industry": candidate.get("industry"),
            "rank": _ranked(symbol, candidate.get("exchange")),
            "name_score": matched_name,
            "exact_symbol": exact_symbol,
        })

    scored.sort(key=lambda c: (
        c["rank"],                    # exchange hierarchy first
        -c["name_score"],             # then confidence it's the right company
        0 if c["exact_symbol"] else 1,
        len(c["symbol"]),
    ))
    return scored


def resolve(short_name: str, catalogue_name: str | None = None, *, validate=True) -> dict | None:
    """Find the best Yahoo listing for one of our short_names.

    Searches by ticker, then by company name if the ticker alone found nothing
    convincing (our short_names are often local codes like `6RJ0` or `TL0` that
    Yahoo has never heard of). The winner is confirmed to actually quote before
    being accepted, so we never cache a symbol that returns no data.
    """
    name = catalogue_name or short_name
    seen: dict[str, dict] = {}

    for query in _queries(short_name, name):
        for candidate in yahoo.search(query).get("quotes", []):
            symbol = candidate.get("symbol")
            if symbol and symbol not in seen:
                seen[symbol] = candidate
        ranked = score_candidates(short_name, name, list(seen.values()))
        if ranked and ranked[0]["rank"] <= 1:
            break
        # Anything below a US primary is worth one more search by company name:
        # our short_names are often local codes (`6RJ0` is Rocket Lab's German
        # line) whose US listing only turns up when you search the name.

    ranked = score_candidates(short_name, name, list(seen.values()))
    if not ranked:
        print(f"[symbols] no listing found for {short_name} ({name})")
        return None

    if not validate:
        return ranked[0]

    # Confirm the pick actually returns prices; fall through the ranking if not.
    for candidate in ranked[:4]:
        quote = yahoo.chart(candidate["symbol"], range_="5d", interval="1d")
        if quote and quote.get("price"):
            return {
                **candidate,
                "exchange": quote.get("exchange") or candidate["exchange"],
                "currency": quote.get("currency"),
                "quote": quote,
            }
        print(f"[symbols] {candidate['symbol']} ranked best for {short_name} but has no quote")

    return None


def _queries(short_name: str, name: str) -> list[str]:
    queries = [short_name]
    trimmed = name.strip()
    if trimmed and trimmed.lower() != short_name.lower():
        queries.append(trimmed)
    return queries

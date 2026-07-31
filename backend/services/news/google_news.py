"""Google News RSS — the broadest free per-ticker news source there is.

Two things worth knowing:

**Backfill by date window.** `when:2d` only reaches back two days, but
`after:/before:` accepts arbitrary dates, and each window returns its own 100
entries. Walking a month in weekly windows therefore yields far more than one
big query ever would — that's how a newly followed stock gets a month of
history in five requests.

**Links are not article URLs.** Since Google's redirect format changed, the
`/rss/articles/CBMi…` payload is an opaque token, not a base64 URL, and turning
it into the publisher's link needs a POST per article. The token *does*
redirect correctly in a browser, so the link is kept as-is and attribution
comes from the feed's `<source>` element instead (see publishers.py). Zero
extra requests, correct publisher, working link.
"""
from __future__ import annotations

from datetime import timedelta

import feedparser

from normalize import domain_of, now_utc, parse_datetime

from ..http_client import scraper
from .publishers import domain_for

SOURCE_TYPE = "GOOGLE_NEWS"
_RSS = "https://news.google.com/rss/search"

# Same corpus, different editions. Rotating the edition across windows spreads
# load over two cache keys and surfaces slightly different outlet mixes.
_EDITIONS = [
    {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    {"hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
]

_WINDOW_DAYS = 7
_MAX_PER_WINDOW = 100


def build_query(short_name: str, company_name: str) -> str:
    """Precise enough to trust, loose enough to find things.

    The company name as a phrase carries the precision. A bare ticker would
    wreck it — searching `APP` or `F` matches most of the internet — so tickers
    only appear inside `"TICKER stock"` / `"TICKER shares"` phrases.
    """
    name = (company_name or "").strip()
    ticker = short_name.strip()
    terms = []
    if name:
        terms.append(f'"{name}"')
    if ticker and ticker.lower() != name.lower():
        terms.append(f'"{ticker} stock"')
        terms.append(f'"{ticker} shares"')
    return " OR ".join(terms) or f'"{ticker}"'


def fetch_recent(short_name: str, company_name: str, days: int = 2) -> list[dict]:
    """Incremental pull: one request for the last couple of days."""
    query = f"{build_query(short_name, company_name)} when:{max(1, days)}d"
    return _fetch(query, _EDITIONS[0])


def fetch_window(short_name: str, company_name: str, after: str, before: str,
                 edition: int = 0) -> list[dict]:
    """`after`/`before` are YYYY-MM-DD, exclusive/inclusive per Google."""
    query = f"{build_query(short_name, company_name)} after:{after} before:{before}"
    return _fetch(query, _EDITIONS[edition % len(_EDITIONS)])


def fetch_backfill(short_name: str, company_name: str, days: int = 30) -> list[dict]:
    """Walk back `days` in weekly windows, newest first.

    Windows are fetched concurrently — they hit one host, so the per-host token
    bucket still paces them; this just stops five sequential round trips.
    """
    today = now_utc().date()
    windows = []
    for index, start in enumerate(range(0, max(days, 1), _WINDOW_DAYS)):
        before = today - timedelta(days=start)
        after = today - timedelta(days=min(start + _WINDOW_DAYS, days))
        if after >= before:
            continue
        query = f"{build_query(short_name, company_name)} after:{after.isoformat()} before:{before.isoformat()}"
        edition = _EDITIONS[index % len(_EDITIONS)]
        windows.append({"url": _RSS, "params": {"q": query, **edition}})

    responses = scraper.get_many(windows)
    articles: list[dict] = []
    for response in responses:
        if response and response.ok:
            articles += _parse(response.text)
    return articles


def _fetch(query: str, edition: dict) -> list[dict]:
    response = scraper.get(_RSS, params={"q": query, **edition})
    if not response or not response.ok:
        return []
    return _parse(response.text)


def _parse(xml: str) -> list[dict]:
    feed = feedparser.parse(xml)
    articles = []

    for entry in feed.entries[:_MAX_PER_WINDOW]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link")
        if not title or not link:
            continue

        publisher = (entry.get("source") or {}).get("title") or "Google News"
        published = parse_datetime(entry.get("published") or entry.get("updated"))
        # Google appends " - Outlet" to every headline; strip it once here so
        # the stored title is clean and dedup compares like with like.
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3].strip()

        articles.append({
            "title": title,
            "url": link,
            "published_at": published,
            "description": None,
            "image": None,
            "source": publisher,
            "source_domain": domain_for(publisher) or domain_of(link),
            "source_type": SOURCE_TYPE,
        })

    return articles

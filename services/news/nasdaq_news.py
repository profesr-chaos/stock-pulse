"""Nasdaq's per-ticker RSS feed.

Carries wire copy (RTTNews, Zacks) and Nasdaq's own editorial with real
article URLs and summaries, on a host nobody else here touches — so it keeps
working through a Google or Yahoo outage.

**It is not trustworthy for unnamed articles.** Asking for `ZZZZQQ` returns
fifteen perfectly real but entirely generic market stories ("Arabica Coffee
Prices Slide…") rather than an empty feed, exactly like Yahoo's symbol-keyed
endpoints. So this source is deliberately left out of `dedup._RELATED_ALLOWED`:
its articles must name the stock to be stored.

US listings only, so callers skip it for everything else.
"""
from __future__ import annotations

import feedparser

from normalize import domain_of, parse_datetime

from ..http_client import scraper

SOURCE_TYPE = "NASDAQ"
_RSS = "https://www.nasdaq.com/feed/rssoutbound"
_MAX_ENTRIES = 30


def fetch(ticker: str) -> list[dict]:
    """`ticker` should be the plain US symbol (no exchange suffix)."""
    response = scraper.get(_RSS, params={"symbol": ticker})
    if not response or not response.ok:
        return []
    return parse(response.text)


def parse(xml: str) -> list[dict]:
    """Split from fetch so it can be tested against a saved feed."""
    feed = feedparser.parse(xml)
    articles = []

    for entry in feed.entries[:_MAX_ENTRIES]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link")
        if not title or not link:
            continue

        domain = domain_of(link)
        articles.append({
            "title": title,
            "url": link,
            "published_at": parse_datetime(entry.get("published") or entry.get("updated")),
            "description": (entry.get("summary") or "").strip() or None,
            "image": None,
            "source": "Nasdaq",
            "source_domain": domain or "nasdaq.com",
            "source_type": SOURCE_TYPE,
        })

    return articles

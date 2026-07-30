"""Yahoo Finance news, via two endpoints that complement each other.

The search JSON carries thumbnails, which is the only free source of article
images we get without fetching each page. The per-ticker RSS carries summaries.
Both give real publisher URLs, so they act as the attributed counterweight to
Google News's opaque redirects.
"""
from __future__ import annotations

import feedparser

from normalize import domain_of, parse_datetime

from .. import yahoo
from .publishers import domain_for

SEARCH_TYPE = "YAHOO_SEARCH"
RSS_TYPE = "YAHOO_RSS"


def fetch_search(symbol: str, limit: int = 20) -> list[dict]:
    """Yahoo's autocomplete news block. Thumbnails included."""
    items = yahoo.search(symbol, quotes=0, news=limit).get("news") or []
    articles = []

    for item in items:
        title = (item.get("title") or "").strip()
        link = item.get("link")
        if not title or not link:
            continue

        publisher = item.get("publisher") or "Yahoo Finance"
        articles.append({
            "title": title,
            "url": link,
            "published_at": parse_datetime(item.get("providerPublishTime")),
            "description": None,
            "image": _best_thumbnail(item.get("thumbnail")),
            "source": publisher,
            "source_domain": domain_for(publisher) or domain_of(link),
            "source_type": SEARCH_TYPE,
        })

    return articles


def _best_thumbnail(thumbnail) -> str | None:
    """Widest resolution offered — these end up as feed hero images."""
    if not isinstance(thumbnail, dict):
        return None
    resolutions = thumbnail.get("resolutions") or []
    usable = [r for r in resolutions if isinstance(r, dict) and r.get("url")]
    if not usable:
        return None
    return max(usable, key=lambda r: r.get("width") or 0)["url"]


def fetch_rss(symbol: str) -> list[dict]:
    """Per-ticker RSS. Older endpoint, still live, and it has summaries."""
    response = yahoo.rss_headlines(symbol)
    if not response or not response.ok:
        return []

    feed = feedparser.parse(response.text)
    articles = []

    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = entry.get("link")
        if not title or not link:
            continue

        summary = (entry.get("summary") or "").strip() or None
        domain = domain_of(link)
        articles.append({
            "title": title,
            "url": link,
            "published_at": parse_datetime(entry.get("published") or entry.get("updated")),
            "description": _clean_summary(summary),
            "image": None,
            "source": _publisher_from_domain(domain),
            "source_domain": domain,
            "source_type": RSS_TYPE,
        })

    return articles


def _clean_summary(summary: str | None) -> str | None:
    if not summary:
        return None
    from bs4 import BeautifulSoup
    text = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
    return text[:600] or None


def _publisher_from_domain(domain: str) -> str:
    if not domain or domain.endswith("yahoo.com"):
        return "Yahoo Finance"
    return domain.removeprefix("www.")

"""Bing News RSS — a second search index, independent of Google.

Worth having for exactly one reason: it is not Google. The two crawls disagree
often enough that their union is meaningfully larger than either, and when
Google News throttles us Bing is unaffected — different company, different
infrastructure, different rate limit.

Unlike Google's opaque `/rss/articles/CBMi…` tokens, Bing's redirect carries
the real article URL in a query parameter, so unwrapping it costs no extra
request. That means Bing items arrive with the publisher's own link, domain
and thumbnail, which makes them *win* dedup tie-breaks that a Google copy of
the same story would lose.
"""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

import feedparser

from normalize import domain_of, parse_datetime

from ..http_client import scraper
from .publishers import domain_for

SOURCE_TYPE = "BING_NEWS"
_RSS = "https://www.bing.com/news/search"
_MAX_ENTRIES = 50


def build_query(short_name: str, company_name: str) -> str:
    """Deliberately *not* google_news.build_query.

    Google's `"X" OR "Y stock" OR "Y shares"` returns a well-populated feed
    there and an empty one here — Bing's news RSS quietly answers a multi-term
    OR with zero items. A single quoted phrase plus the word `stock` returns a
    full feed for every ticker tried, so this keeps the phrase precision and
    drops the OR.
    """
    name = (company_name or "").strip()
    ticker = (short_name or "").strip()
    if name:
        return f'"{name}" stock'
    return f'"{ticker}" stock' if ticker else ""


def fetch(short_name: str, company_name: str, days: int = 2) -> list[dict]:
    """`days` is accepted for symmetry with the other sources.

    Bing has no date operator worth trusting, so it always returns its most
    recent matches; the caller's retention and dedup handle the rest.
    """
    query = build_query(short_name, company_name)
    if not query:
        return []
    response = scraper.get(_RSS, params={"q": query, "format": "RSS"})
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

        url = unwrap(link)
        publisher = (entry.get("news_source") or "").strip()
        domain = domain_of(url)
        # An unwrapped link already carries the true domain; fall back to the
        # publisher name only when unwrapping failed.
        if not domain or domain.endswith("bing.com"):
            domain = domain_for(publisher)

        articles.append({
            "title": title,
            "url": url,
            "published_at": parse_datetime(entry.get("published") or entry.get("updated")),
            "description": (entry.get("summary") or "").strip() or None,
            "image": entry.get("news_image") or None,
            "source": publisher or domain or "Bing News",
            "source_domain": domain,
            "source_type": SOURCE_TYPE,
        })

    return articles


def unwrap(link: str) -> str:
    """`bing.com/news/apiclick.aspx?…&url=<encoded>` → the publisher's URL.

    Anything unexpected is returned untouched: a working redirect is better
    than a mangled link.
    """
    if "bing.com" not in link:
        return link
    target = parse_qs(urlsplit(link).query).get("url")
    if not target or not target[0]:
        return link
    unwrapped = unquote(target[0])
    return unwrapped if unwrapped.startswith(("http://", "https://")) else link

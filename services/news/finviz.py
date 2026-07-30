"""Finviz quote-page news table.

Worth scraping because it lists the publisher's *real* URL — investors.com,
barrons.com, marketwatch.com — which makes it the best source for the dedup
tie-breaker, and it's dense (dozens of items per US ticker).

US coverage only, so callers skip it for non-US listings.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from normalize import domain_of, now_utc

from ..http_client import scraper
from .publishers import domain_for

SOURCE_TYPE = "FINVIZ"
_URL = "https://finviz.com/quote.ashx"
_BASE = "https://finviz.com"

# Finviz timestamps are US market time, with no zone marker on the page.
_MARKET_TZ = ZoneInfo("America/New_York")

_DATE_TIME = re.compile(r"^([A-Za-z]{3}-\d{2}-\d{2}|Today|Yesterday)\s+(\d{1,2}:\d{2}(?:AM|PM))$", re.I)
_TIME_ONLY = re.compile(r"^(\d{1,2}:\d{2}(?:AM|PM))$", re.I)


def fetch(symbol: str) -> list[dict]:
    """`symbol` should be the plain US ticker (no exchange suffix)."""
    response = scraper.get(_URL, params={"t": symbol, "p": "d"})
    if not response or not response.ok:
        return []
    return parse(response.text)


def parse(html: str) -> list[dict]:
    """Split from fetch so it can be tested against a saved page."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="news-table")
    if not table:
        return []

    articles = []
    current_date = None      # rows after the first of a day carry time only

    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        anchor = tr.find("a")
        if not anchor or not anchor.get("href"):
            continue

        title = anchor.get_text(strip=True)
        if not title:
            continue

        published, current_date = _parse_stamp(cells[0].get_text(strip=True), current_date)

        url = anchor["href"]
        if url.startswith("/"):
            url = _BASE + url

        publisher = _publisher(tr)
        domain = domain_of(url)
        # A finviz.com-hosted item is Finviz's own copy; prefer the publisher
        # name we can read off the row.
        if domain == "finviz.com":
            domain = domain_for(publisher) or domain

        articles.append({
            "title": title,
            "url": url,
            "published_at": published,
            "description": None,
            "image": None,
            "source": publisher or domain or "Finviz",
            "source_domain": domain,
            "source_type": SOURCE_TYPE,
        })

    return articles


def _publisher(tr) -> str:
    span = tr.find("span")
    if not span:
        return ""
    return span.get_text(strip=True).strip("()").strip()


def _parse_stamp(text: str, current_date) -> tuple[datetime | None, object]:
    """Returns (utc datetime, date to carry into the next rows)."""
    text = text.replace("\xa0", " ").strip()

    if match := _DATE_TIME.match(text):
        day_text, time_text = match.group(1), match.group(2)
        day = _parse_day(day_text)
        return _combine(day, time_text), day

    if match := _TIME_ONLY.match(text):
        if current_date is None:
            return None, current_date
        return _combine(current_date, match.group(1)), current_date

    return None, current_date


def _parse_day(text: str):
    today = now_utc().astimezone(_MARKET_TZ).date()
    lowered = text.lower()
    if lowered == "today":
        return today
    if lowered == "yesterday":
        return today - timedelta(days=1)
    try:
        return datetime.strptime(text, "%b-%d-%y").date()
    except ValueError:
        return None


def _combine(day, time_text: str) -> datetime | None:
    if day is None:
        return None
    try:
        clock = datetime.strptime(time_text.upper(), "%I:%M%p").time()
    except ValueError:
        return None
    from normalize import UTC
    return datetime.combine(day, clock, tzinfo=_MARKET_TZ).astimezone(UTC)

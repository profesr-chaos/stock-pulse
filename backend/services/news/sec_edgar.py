"""SEC EDGAR filings — the primary source, before anyone reports on it.

Every other source in this package is somebody's write-up of an event. EDGAR
is the event: the 8-K lands here first and the headlines follow. It is also
the only source that cannot go stale, be paywalled, or quietly drop a story.

Two things shape this module:

**Titles are useless as filed.** An entry's title is `"8-K  - Current report"`
— no company, no ticker. Stored as-is, every relevance check would drop it and
every dedup key would collide with every other company's 8-K. So the title is
constructed from the company name and the form.

**Most filings are noise.** Forms 3/4/5 and 144 are routine insider paperwork,
dozens a month, and would swamp a feed. Only the forms that move a price are
kept — see `_MATERIAL_FORMS`.

SEC's fair-access policy requires a declared identity with contact details on
every request, and enforces it: a User-Agent carrying a repo URL rather than an
email gets a flat 403. So this source is opt-in on `STOCKY_SEC_CONTACT` and
skips itself when that is unset, rather than hammering a regulator that asked
to know who we are with requests that will be refused anyway.
"""
from __future__ import annotations

import feedparser

import settings
from normalize import parse_datetime

from ..http_client import scraper

SOURCE_TYPE = "SEC_EDGAR"
_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
_MAX_ENTRIES = 25

# Prefixes, so amendments (`8-K/A`) and series (`424B5`) come along for free.
_MATERIAL_FORMS = (
    "8-K",      # material event — the one that moves prices
    "10-K",     # annual report
    "10-Q",     # quarterly report
    "6-K",      # foreign private issuer interim report
    "20-F",     # foreign private issuer annual report
    "40-F",     # Canadian annual report
    "425",      # merger / business combination communication
    "DEF 14A",  # proxy statement
    "DEFM14A",  # merger proxy
    "SC 13D",   # activist stake
    "SC TO",    # tender offer
    "S-1",      # registration — IPO or new shares
    "S-3",      # shelf registration
    "424B",     # prospectus supplement, i.e. an actual raise
)


def fetch(ticker: str, company_name: str) -> list[dict]:
    """`ticker` is the plain US symbol — EDGAR resolves it to a CIK itself."""
    if not settings.sec_enabled():
        return []

    response = scraper.get(
        _URL,
        params={
            "action": "getcompany", "CIK": ticker, "type": "", "dateb": "",
            "owner": "include", "count": _MAX_ENTRIES, "output": "atom",
        },
        headers={"User-Agent": settings.SEC_USER_AGENT,
                 "Accept": "application/atom+xml,application/xml"},
    )
    if not response or not response.ok:
        return []
    return parse(response.text, company_name or ticker)


def parse(xml: str, company_name: str) -> list[dict]:
    """Split from fetch so it can be tested against a saved feed.

    An unknown ticker gets an HTML "no matching companies" page back with a 200
    status; feedparser finds no entries in it, so that lands here as [].
    """
    feed = feedparser.parse(xml)
    articles = []

    for entry in feed.entries[:_MAX_ENTRIES]:
        form = (entry.get("filing-type") or "").strip()
        link = entry.get("filing-href") or entry.get("link")
        if not form or not link or not is_material(form):
            continue

        description = (entry.get("form-name") or "").strip()
        articles.append({
            "title": _title(company_name, form, description),
            "url": link,
            "published_at": parse_datetime(entry.get("filing-date")),
            "description": description or None,
            "image": None,
            "source": "SEC EDGAR",
            "source_domain": "sec.gov",
            "source_type": SOURCE_TYPE,
        })

    return articles


def is_material(form: str) -> bool:
    upper = form.upper().strip()
    return any(upper.startswith(prefix) for prefix in _MATERIAL_FORMS)


def _title(company_name: str, form: str, form_name: str) -> str:
    """"Apple Inc. filed 8-K: Current report".

    Naming the company is what makes the item survive the relevance filter and
    dedup on the right key, so it is not cosmetic.
    """
    suffix = f": {form_name}" if form_name else ""
    return f"{company_name} filed {form}{suffix}"

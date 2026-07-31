"""Turn raw scraped articles into clean, story-level rows.

This is the module that fixes the original complaint: fifty outlets carrying one
wire story should appear once, as the best copy of it.

What went wrong before: duplicate detection ran at insert time, comparing each
incoming headline against every headline stored in the previous seven days
*across every stock*, at 75% similarity. "Stock Market Today: Nasdaq Rises" for
NVDA therefore blocked the near-identical TSLA headline permanently, and the
whole database held 332 articles.

What happens now:

* Deduplication is scoped to **one stock and a ±72 hour window** — the only
  scope in which two similar headlines are actually the same story.
* Identity is a **canonical URL hash** (tracking parameters stripped), enforced
  by a DB unique index rather than a fuzzy scan.
* Near-duplicates are **clustered**, and each cluster elects a winner by source
  quality, then by whether it has an image and a description. So the Reuters
  copy wins over the content-farm rewrite.
* When a new article duplicates one already stored, it is not inserted — but if
  it carries an image or description the stored row lacks, that row is
  **enriched** instead. Nothing useful is thrown away.
* Relevance filtering applies only to sources that can bleed (a Google text
  query). Symbol-keyed sources are trusted, so "Chip stocks slide on AI fears"
  survives for NVDA even though it names neither the ticker nor the company.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta

from rapidfuzz import fuzz

from normalize import (
    domain_of,
    now_utc,
    parse_datetime,
    source_rank,
    title_key,
    title_tokens,
    to_iso,
    url_hash,
)

# Two headlines are the same story if they share a normalised key, or read
# almost the same. token_set_ratio already ignores word order and padding, so
# this can sit high without missing rewrites.
_SIMILARITY_THRESHOLD = 88
_CLUSTER_WINDOW = timedelta(hours=72)

# Which sources may contribute an article that never names the stock.
#
# Finviz's quote page is a genuinely hand-curated per-ticker table, so an
# unnamed item there is real sector context — "Space stocks are falling hard"
# matters to a Rocket Lab holder, and is kept as `related`.
#
# Yahoo's search and RSS endpoints look symbol-keyed but silently fall back to
# generic market news when they have nothing for a ticker: asking for IVU.DE
# returned "Warsh-led Fed leaves rates on hold" and a Jersey Mike's IPO notice.
# So they, like Google News, must name the stock to count.
_RELATED_ALLOWED = frozenset({"FINVIZ"})

DIRECT = "direct"
RELATED = "related"

# The dominant false positive from symbol-keyed sources is an article about a
# different company entirely: Yahoo's news search for RKLB returned "IBRX Stock
# Extends 5-Day Losing Streak". Such headlines lead with the other ticker.
#
# The leading group is deliberately case-*sensitive*: tickers are written in
# caps. With IGNORECASE it also matched ordinary capitalised words, so "Space
# stocks are falling hard" and "Tesla shares rise" were read as other
# companies' tickers and dropped.
_LEADS_WITH_TICKER = re.compile(
    r"^\(?([A-Z]{1,5})\)?[:,]?\s+(?:[Ss]tock|[Ss]hares|[Ss]hare|[Ee]arnings|[Qq][1-4]\b)"
)

# Only unambiguous advertising. Press releases are deliberately *not* filtered:
# a company's own earnings release is often the most important item of the day,
# and the previous version discarded all of them.
_SPAM_MARKERS = (
    "sponsored content", "sponsored by", "advertorial", "paid content",
    "paid post", "promoted content", "partner content", "brandpost",
    "sponsored:", "[ad]", "(ad)", "advertisement",
)

_MIN_TITLE_LENGTH = 15

# Generic corporate scaffolding, dropped before matching a company name.
_LEGAL_SUFFIXES = frozenset("""
inc inc. incorporated corp corp. corporation ltd ltd. limited llc plc co co.
company group holdings holding holdings. sa nv ag ab asa oyj spa se kgaa
class cls shs shares ordinary ord adr ads reit trust fund etf plc.
""".split())


@dataclass
class Prepared:
    """The result of preparing a batch for one stock."""
    rows: list[dict] = field(default_factory=list)
    enrichments: dict[int, dict] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)

    def count(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1


# ── Relevance and spam ───────────────────────────────────────────────────

def company_keywords(company_name: str) -> list[str]:
    """Distinctive words of a company name.

    "Eldorado Gold Corp" → ["eldorado", "gold"]; "Apple Inc." → ["apple"].
    """
    words = re.sub(r"[^\w\s&]", " ", (company_name or "").lower()).split()
    keywords = [w for w in words if w not in _LEGAL_SUFFIXES and len(w) > 1]
    return keywords or words[:1]


def is_relevant(text: str, short_name: str, company_name: str,
                aliases: tuple[str, ...] = ()) -> bool:
    """Does this text name the stock?

    Whole-word matching throughout, so "apples" doesn't match "AAPL" and
    "application" doesn't match "APP".

    `aliases` matters more than it looks: our short_name is whatever Trading212
    called the instrument, so Rocket Lab is `6RJ0` locally while every article
    says `RKLB`. Without the resolved symbol as an alias, nothing would match.
    """
    lowered = text.lower()

    for ticker in (short_name, *aliases):
        if ticker and _whole_word(ticker.lower(), lowered):
            return True

    keywords = company_keywords(company_name)
    if keywords and all(_whole_word(k, lowered) for k in keywords):
        return True

    # A distinctive single-word name is enough on its own ("Nvidia", "Tesla").
    if len(keywords) == 1 and len(keywords[0]) >= 5 and _whole_word(keywords[0], lowered):
        return True

    return False


def focuses_on_other_stock(title: str, short_name: str,
                           aliases: tuple[str, ...] = ()) -> bool:
    """True when a headline is plainly *about* a different ticker.

    Only fires on the leading-ticker pattern ("IBRX Stock Extends…"), so
    sector pieces that never name a ticker are unaffected.
    """
    match = _LEADS_WITH_TICKER.match(title.strip())
    if not match:
        return False
    leading = match.group(1).upper()
    ours = {short_name.upper(), *(a.upper() for a in aliases if a)}
    return leading not in ours


def _whole_word(needle: str, haystack: str) -> bool:
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def is_spam(article: dict) -> bool:
    title = article.get("title") or ""
    if len(title.strip()) < _MIN_TITLE_LENGTH:
        return True
    blob = f"{title} {article.get('description') or ''}".lower()
    return any(marker in blob for marker in _SPAM_MARKERS)


# ── Clustering ───────────────────────────────────────────────────────────

def same_story(a: dict, b: dict) -> bool:
    """Whether two articles report the same story.

    Callers must already have limited comparison to one stock; this only adds
    the time window and the textual test.
    """
    if a.get("url_hash") and a["url_hash"] == b.get("url_hash"):
        return True

    when_a, when_b = a.get("_when"), b.get("_when")
    if when_a and when_b and abs(when_a - when_b) > _CLUSTER_WINDOW:
        return False

    key_a, key_b = a.get("title_key"), b.get("title_key")
    if key_a and key_a == key_b:
        return True

    return fuzz.token_set_ratio(a.get("title", ""), b.get("title", "")) >= _SIMILARITY_THRESHOLD


def quality(article: dict) -> tuple:
    """Sort key electing a cluster winner. Lower is better.

    An article that names the stock outranks sector context, then source
    trustworthiness — a Reuters report beats an aggregator's rewrite of it even
    if the rewrite has a nicer picture.
    """
    return (
        0 if article.get("relevance", DIRECT) == DIRECT else 1,
        source_rank(article.get("source_domain") or ""),
        0 if article.get("image") else 1,
        0 if article.get("description") else 1,
        len(article.get("title") or ""),
    )


# ── Preparation ──────────────────────────────────────────────────────────

def prepare(
    articles: list[dict],
    short_name: str,
    company_name: str,
    existing: list[dict] | None = None,
    aliases: tuple[str, ...] = (),
) -> Prepared:
    """Clean, dedupe and cluster a batch of scraped articles for one stock.

    `existing` comes from db.news.get_recent_fingerprints, so incoming articles
    are compared against what is already stored, not just against each other.
    `aliases` should include the resolved exchange symbol.
    """
    result = Prepared()
    candidates: list[dict] = []
    seen_hashes: set[str] = set()

    for raw in articles:
        article = _normalise(raw, short_name)
        if article is None:
            result.count("malformed")
            continue

        blob = f"{article['title']} {article.get('description') or ''}"
        names_the_stock = is_relevant(blob, short_name, company_name, aliases)

        if not names_the_stock:
            if article["source_type"] not in _RELATED_ALLOWED:
                result.count("off_topic")
                continue
            # Even a curated table sometimes lists another company's story.
            if focuses_on_other_stock(article["title"], short_name, aliases):
                result.count("other_stock")
                continue

        article["relevance"] = DIRECT if names_the_stock else RELATED

        if is_spam(article):
            result.count("spam")
            continue

        if article["url_hash"] in seen_hashes:
            result.count("duplicate_url")
            continue
        seen_hashes.add(article["url_hash"])
        candidates.append(article)

    # Best copy first, so the first article to claim a cluster is its winner.
    candidates.sort(key=quality)

    stored = [_normalise_existing(e) for e in (existing or [])]
    clusters: list[dict] = []

    for article in candidates:
        match = _find(stored, article)
        if match is not None:
            # Already have this story: keep the stored row, top it up.
            enrichment = _enrichment(match, article)
            if enrichment:
                result.enrichments[match["id"]] = {
                    **result.enrichments.get(match["id"], {}), **enrichment
                }
            result.count("already_stored")
            continue

        if _find(clusters, article) is not None:
            result.count("duplicate_story")
            continue

        clusters.append(article)
        result.rows.append(_to_row(article))

    return result


def _find(pool: list[dict], article: dict) -> dict | None:
    for other in pool:
        if same_story(article, other):
            return other
    return None


def _enrichment(stored: dict, incoming: dict) -> dict:
    """Fields the incoming copy has and the stored row is missing."""
    fields = {}
    if incoming.get("image") and not stored.get("has_image"):
        fields["image"] = incoming["image"]
    if incoming.get("description") and not stored.get("has_description"):
        fields["description"] = incoming["description"]
    return fields


def _normalise(raw: dict, short_name: str) -> dict | None:
    title = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    if not title or not url:
        return None

    when = raw.get("published_at")
    if not hasattr(when, "tzinfo"):
        when = parse_datetime(when)
    # No date at all means we can't place it in the feed; treat as now rather
    # than discard, since scraped pages sometimes omit it.
    when = when or now_utc()
    if when > now_utc() + timedelta(hours=6):
        return None  # bogus future date

    return {
        "short_name": short_name,
        "title": title,
        "title_key": title_key(title),
        "url": url,
        "url_hash": url_hash(url),
        "description": (raw.get("description") or None),
        "image": raw.get("image") or None,
        "source": raw.get("source") or "Unknown",
        "source_domain": raw.get("source_domain") or domain_of(url),
        "source_type": raw.get("source_type") or "SCRAPE",
        "_when": when,
    }


def _normalise_existing(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row.get("title") or "",
        "title_key": row.get("title_key") or "",
        "url_hash": row.get("url_hash") or "",
        "source_domain": row.get("source_domain") or "",
        "has_image": bool(row.get("has_image")),
        "has_description": bool(row.get("has_description")),
        "_when": parse_datetime(row.get("publish_time")),
    }


def _to_row(article: dict) -> dict:
    return {
        "short_name": article["short_name"],
        "title": article["title"],
        "title_key": article["title_key"],
        "url": article["url"],
        "url_hash": article["url_hash"],
        "description": article["description"],
        "image": article["image"],
        "source": article["source"],
        "source_domain": article["source_domain"],
        "source_type": article["source_type"],
        "source_url": f"https://{article['source_domain']}" if article["source_domain"] else None,
        "publish_time": to_iso(article["_when"]),
        "relevance": article.get("relevance", DIRECT),
        "lang": "en",
    }


def has_meaningful_tokens(title: str, minimum: int = 4) -> bool:
    """Exposed for tests: whether a headline carries enough substance for its
    normalised key to be a safe dedup signal."""
    return len(set(title_tokens(title))) >= minimum

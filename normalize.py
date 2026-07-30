"""Pure text/date/URL normalisation. No I/O, no DB, no config — so both the
db layer and the scrapers can import it without a cycle, and it is trivially
testable.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UTC = timezone.utc


# ── Time ─────────────────────────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return to_iso(now_utc())


def to_iso(dt: datetime) -> str:
    """Canonical storage format: UTC, second precision, trailing Z.

    One format everywhere means `ORDER BY publish_time` and string `>=`
    comparisons are correct, which is what the old mixed RFC-822/ISO storage
    silently broke.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value) -> datetime | None:
    """Best-effort parse of anything a feed or scraped page hands us.

    Handles ISO 8601 (with or without Z), RFC 822 (`Wed, 28 Jan 2026 22:07:57
    +0000`), and epoch seconds/milliseconds. Naive values are assumed UTC.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    # epoch seconds or milliseconds
    if isinstance(value, (int, float)):
        return _from_epoch(value)

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        return _from_epoch(int(text))

    # ISO first: cheapest and by far the most common.
    try:
        return _aware(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass

    # RFC 822 / 2822, as used by virtually every RSS feed.
    try:
        return _aware(parsedate_to_datetime(text))
    except (TypeError, ValueError):
        pass

    # Loose fallbacks for scraped pages.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%b-%d-%y %I:%M%p", "%b %d, %Y", "%d %b %Y"):
        try:
            return _aware(datetime.strptime(text, fmt))
        except ValueError:
            continue

    return None


def _from_epoch(value: float) -> datetime | None:
    # 1e11 seconds is year 5138, so anything larger is milliseconds.
    seconds = value / 1000 if abs(value) > 1e11 else value
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_iso(value) -> datetime | None:
    """Alias used at call sites that only ever see our own stored format."""
    return parse_datetime(value)


def days_ago_iso(days: int) -> str:
    return to_iso(now_utc() - timedelta(days=days))


def day_str(dt: datetime | date | None = None) -> str:
    """YYYY-MM-DD in UTC."""
    if dt is None:
        dt = now_utc()
    if isinstance(dt, datetime):
        dt = dt.astimezone(UTC).date()
    return dt.isoformat()


# ── URLs ─────────────────────────────────────────────────────────────────

# Tracking junk that makes the same article look like several.
_TRACKING_PARAMS = re.compile(
    r"^(utm_|ic[Ii][Dd]$|icid_|cmp$|cmpid$|ns_|at_|fbclid$|gclid$|mc_|"
    r"ref$|ref_src$|referrer$|source$|sh$|yptr$|guccounter$|_ga$|spm$|"
    r"__twitter_impression$|smid$|partner$|taid$|tsrc$|mod$|siteid$|"
    r"link$|reflink$|mkt_tok$|CMP$)"
)


def canonical_url(url: str) -> str:
    """Strip the noise that makes one article look like many.

    Lowercases scheme/host, drops `www.`, removes tracking params, sorts the
    survivors, drops the fragment and any trailing slash.
    """
    if not url:
        return ""
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"

    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=False)
            if not _TRACKING_PARAMS.match(k)
        )
    )

    path = parts.path.rstrip("/") or "/"
    return urlunsplit(((parts.scheme or "https").lower(), host, path, query, ""))


def url_hash(url: str) -> str:
    """Stable 16-byte digest of the canonical URL — the news uniqueness key."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:32]


def domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# ── Titles ───────────────────────────────────────────────────────────────

# Google News appends " - Outlet"; plenty of feeds use " | Outlet".
_OUTLET_SUFFIX = re.compile(r"\s+[-–—|]\s+[^-–—|]{2,40}$")
_NON_WORD = re.compile(r"[^a-z0-9$%. ]+")
_MULTISPACE = re.compile(r"\s+")

# Words that carry no story identity. Deliberately excludes negations and
# finance verbs — "beats" vs "misses" is the whole story.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from by with
about into over after before during under above via as is are was were be been being
am do does did doing have has had having will would shall should can could may might must
it its it's he she they them their his her our your my i you we us
s t d ll m re ve y new news says say said report reports reported update updates
amid ahead here what why how when who which more most just now today
""".split())


def strip_outlet_suffix(title: str) -> str:
    """`Apple beats estimates - Reuters` → `Apple beats estimates`."""
    if not title:
        return ""
    cleaned = _OUTLET_SUFFIX.sub("", title.strip())
    # Never strip the title down to nothing (short headlines are all suffix-shaped).
    return cleaned.strip() if len(cleaned) >= 12 else title.strip()


def title_tokens(title: str) -> list[str]:
    """Content words of a headline, lowercased, digits kept.

    Digits stay because `recalls 200K vehicles` and `recalls 50K vehicles` are
    different stories.
    """
    text = strip_outlet_suffix(title).lower()
    text = text.replace("’", "'").replace("&", " and ")
    text = _NON_WORD.sub(" ", text)
    words = _MULTISPACE.sub(" ", text).strip().split()
    return [w.strip(".") for w in words if w.strip(".") and w.strip(".") not in _STOPWORDS]


def title_key(title: str) -> str:
    """Order-independent fingerprint of a headline.

    Same wire story rewritten by ten outlets usually collapses to the same key.
    Returns "" when the headline has too little substance to be a safe dedup
    signal — callers then fall back to fuzzy matching only.
    """
    tokens = title_tokens(title)
    unique = sorted(set(tokens))
    if len(unique) < 4:
        return ""
    return " ".join(unique[:12])


# ── Source quality ───────────────────────────────────────────────────────

# When several outlets carry the same story, keep the most trustworthy copy.
# Lower is better.
_SOURCE_RANK: dict[str, int] = {
    "reuters.com": 0, "bloomberg.com": 0, "ft.com": 0, "wsj.com": 0,
    "apnews.com": 1, "cnbc.com": 1, "barrons.com": 1, "economist.com": 1,
    "marketwatch.com": 2, "nytimes.com": 2, "theguardian.com": 2, "bbc.co.uk": 2,
    "bbc.com": 2, "telegraph.co.uk": 2, "thetimes.co.uk": 2,
    "investors.com": 3, "seekingalpha.com": 3, "morningstar.com": 3,
    "finance.yahoo.com": 3, "yahoo.com": 3, "forbes.com": 3, "businessinsider.com": 3,
    "fool.com": 4, "zacks.com": 4, "benzinga.com": 4, "investing.com": 4,
    "thestreet.com": 4, "simplywall.st": 4, "tipranks.com": 4, "insidermonkey.com": 5,
    "news.google.com": 6,   # unresolved Google redirect: works, but no attribution
}

_DEFAULT_SOURCE_RANK = 5


def source_rank(domain_or_url: str) -> int:
    domain = domain_or_url if "/" not in domain_or_url else domain_of(domain_or_url)
    if domain in _SOURCE_RANK:
        return _SOURCE_RANK[domain]
    # match subdomains, e.g. uk.reuters.com
    for known, rank in _SOURCE_RANK.items():
        if domain.endswith("." + known):
            return rank
    return _DEFAULT_SOURCE_RANK


# ── Symbols ──────────────────────────────────────────────────────────────

# Leading `^` is allowed because that is how Yahoo names indices (^GSPC,
# ^FTSE), and index funds are part of what this tracks.
_SYMBOL_OK = re.compile(r"^[\^A-Za-z0-9][A-Za-z0-9._-]{0,19}$")


def valid_symbol(symbol: str) -> bool:
    """Guard at the API boundary.

    Symbols are interpolated into outbound scraper URLs, so anything that
    isn't ticker-shaped is rejected before it can reach a third party.
    """
    return bool(symbol and _SYMBOL_OK.match(symbol))


def clean_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()

"""Publisher display name → domain.

Google News hands us a publisher name ("Barron's") and an obfuscated redirect
link, never the article's real URL. Without a domain, every Google item would
look like it came from news.google.com and would lose every dedup tie-break to
the same story fetched from another source. Mapping the name back to a domain
is free and restores proper source ranking.
"""
from __future__ import annotations

import re

_BY_NAME: dict[str, str] = {
    "reuters": "reuters.com",
    "bloomberg": "bloomberg.com",
    "bloomberg.com": "bloomberg.com",
    "financial times": "ft.com",
    "the wall street journal": "wsj.com",
    "wsj": "wsj.com",
    "wsj.com": "wsj.com",
    "the associated press": "apnews.com",
    "associated press": "apnews.com",
    "ap news": "apnews.com",
    "cnbc": "cnbc.com",
    "barron's": "barrons.com",
    "barrons.com": "barrons.com",
    "barrons": "barrons.com",
    "marketwatch": "marketwatch.com",
    "the economist": "economist.com",
    "the new york times": "nytimes.com",
    "the guardian": "theguardian.com",
    "bbc": "bbc.co.uk",
    "bbc news": "bbc.co.uk",
    "the telegraph": "telegraph.co.uk",
    "the times": "thetimes.co.uk",
    "sky news": "news.sky.com",
    "cnn": "cnn.com",
    "fortune": "fortune.com",
    "forbes": "forbes.com",
    "business insider": "businessinsider.com",
    "investor's business daily": "investors.com",
    "investors business daily": "investors.com",
    "yahoo finance": "finance.yahoo.com",
    "yahoo entertainment": "finance.yahoo.com",
    "seeking alpha": "seekingalpha.com",
    "morningstar": "morningstar.com",
    "the motley fool": "fool.com",
    "motley fool": "fool.com",
    "fool.com": "fool.com",
    "zacks investment research": "zacks.com",
    "zacks": "zacks.com",
    "benzinga": "benzinga.com",
    "investing.com": "investing.com",
    "thestreet": "thestreet.com",
    "simply wall st.": "simplywall.st",
    "simply wall st": "simplywall.st",
    "tipranks": "tipranks.com",
    "insider monkey": "insidermonkey.com",
    "stocktwits": "stocktwits.com",
    "quartz": "qz.com",
    "axios": "axios.com",
    "the verge": "theverge.com",
    "techcrunch": "techcrunch.com",
    "ars technica": "arstechnica.com",
    "engadget": "engadget.com",
    "cnet": "cnet.com",
    "wired": "wired.com",
    "space.com": "space.com",
    "spacenews": "spacenews.com",
    "ars technica uk": "arstechnica.com",
    "schaeffer's research": "schaeffersresearch.com",
    "gurufocus": "gurufocus.com",
    "24/7 wall st.": "247wallst.com",
    "proactive investors": "proactiveinvestors.co.uk",
    "city a.m.": "cityam.com",
    "this is money": "thisismoney.co.uk",
    "the motley fool uk": "fool.co.uk",
    "hargreaves lansdown": "hl.co.uk",
    "handelsblatt": "handelsblatt.com",
    "der spiegel": "spiegel.de",
    "boerse online": "boerse-online.de",
    "finanzen.net": "finanzen.net",
    "le monde": "lemonde.fr",
    "les echos": "lesechos.fr",
    "rttnews": "rttnews.com",
    "nasdaq": "nasdaq.com",
    "sec edgar": "sec.gov",
    "invezz": "invezz.com",
    "baystreet.ca": "baystreet.ca",
    "the globe and mail": "theglobeandmail.com",
    "financial post": "financialpost.com",
    "the economic times": "economictimes.indiatimes.com",
    "south china morning post": "scmp.com",
    "msn": "msn.com",
}

_TRAILING_NOISE = re.compile(r"\s*[-–—|]\s*(news|online|finance|markets?)$", re.I)

# Bing attributes republished stories as "The Motley Fool on MSN". The original
# publisher is the useful half — it is what ranks and what dedup should match —
# so the aggregator suffix comes off before the lookup.
_REPUBLISHED_ON = re.compile(r"\s+on\s+(msn|yahoo|aol|flipboard)\b.*$", re.I)


def domain_for(publisher: str | None) -> str:
    """Best-effort domain for a publisher name. "" when unknown."""
    if not publisher:
        return ""
    name = _TRAILING_NOISE.sub("", publisher.strip()).strip().lower()
    if name in _BY_NAME:
        return _BY_NAME[name]

    if (original := _REPUBLISHED_ON.sub("", name).strip()) != name and original in _BY_NAME:
        return _BY_NAME[original]

    # Already a domain, e.g. "reuters.com"
    if "." in name and " " not in name:
        return name.removeprefix("www.")

    # ponytail: unknown publishers get no domain rather than a guessed one — a
    # wrong domain would corrupt source ranking, an empty one just means
    # "average source", which is the honest default.
    return ""

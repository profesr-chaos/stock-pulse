"""Sentiment scoring for financial headlines, in [-1, 1].

Default backend is VADER with a **finance lexicon override**, because
general-purpose VADER is actively wrong on market language: it scores "beat" as
violence and has no idea that "misses estimates", "downgrade" or "guidance cut"
are the whole story. Overriding a few hundred terms fixes that for the price of
a dict and needs no model download — the previous setup pulled ~2.5GB of torch
plus FinBERT to score short headlines, which is also what broke the virtualenv.

FinBERT is still available and is genuinely better on nuanced text: install the
`finbert` extra and set STOCKY_SENTIMENT=finbert. If it is requested but cannot
be loaded, we log and fall back rather than failing a refresh.
"""
from __future__ import annotations

import re
import threading
from uuid import UUID

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

import db
import settings

# VADER's scale is roughly -4 … +4 per token. These are the terms that decide a
# financial headline's direction, with the polarity they carry *in markets*.
FINANCE_LEXICON: dict[str, float] = {
    # results vs expectations — the most common headline pattern there is
    "beat": 2.6, "beats": 2.6, "beating": 2.4, "topped": 2.2, "tops": 2.2,
    "exceeded": 2.4, "exceeds": 2.4, "surpassed": 2.4, "surpasses": 2.4,
    "miss": -2.6, "misses": -2.6, "missed": -2.6, "missing": -2.0,
    "shortfall": -2.6, "disappointing": -2.6, "disappoints": -2.6,
    "inline": 0.0, "in-line": 0.0,
    # price action
    "surge": 2.8, "surges": 2.8, "surged": 2.8, "surging": 2.8,
    "soar": 3.0, "soars": 3.0, "soared": 3.0, "soaring": 3.0,
    "rally": 2.4, "rallies": 2.4, "rallied": 2.4, "rallying": 2.4,
    "jump": 2.2, "jumps": 2.2, "jumped": 2.2, "jumping": 2.0,
    "climb": 1.8, "climbs": 1.8, "climbed": 1.8,
    "rise": 1.6, "rises": 1.6, "rose": 1.6,
    "gain": 1.8, "gains": 1.8, "gained": 1.8,
    "outperform": 2.4, "outperforms": 2.4, "outperformed": 2.4,
    "breakout": 2.0, "rebound": 1.8, "rebounds": 1.8, "recovers": 1.8,
    "undervalued": 1.8, "overvalued": -1.8,
    "plunge": -3.0, "plunges": -3.0, "plunged": -3.0, "plunging": -3.0,
    "plummet": -3.2, "plummets": -3.2, "plummeted": -3.2,
    "tumble": -2.8, "tumbles": -2.8, "tumbled": -2.8, "tumbling": -2.8,
    "slump": -2.6, "slumps": -2.6, "slumped": -2.6, "slumping": -2.6,
    "sink": -2.4, "sinks": -2.4, "sank": -2.4, "sinking": -2.4,
    "slide": -2.2, "slides": -2.2, "slid": -2.2, "sliding": -2.2,
    "fall": -1.8, "falls": -1.8, "fell": -1.8, "falling": -1.8,
    "drop": -1.8, "drops": -1.8, "dropped": -1.8, "dropping": -1.8,
    "decline": -1.8, "declines": -1.8, "declined": -1.8,
    "underperform": -2.4, "underperforms": -2.4,
    "selloff": -2.6, "sell-off": -2.6,
    "crash": -3.4, "crashes": -3.4, "crashed": -3.4,
    "collapse": -3.4, "collapses": -3.4, "collapsed": -3.4,
    "correction": -1.6,
    # analyst actions
    "upgrade": 2.6, "upgrades": 2.6, "upgraded": 2.6,
    "downgrade": -2.6, "downgrades": -2.6, "downgraded": -2.6,
    "overweight": 1.8, "underweight": -1.8,
    "initiated": 0.6, "reiterated": 0.4, "bullish": 2.6, "bearish": -2.6,
    # guidance and capital
    "buyback": 2.2, "buybacks": 2.2, "repurchase": 1.8,
    "dividend": 1.6, "profit": 1.8, "profits": 1.8, "profitable": 2.2,
    "loss": -1.8, "losses": -1.8,
    "writedown": -2.4, "write-down": -2.4, "impairment": -2.2,
    "growth": 1.8, "expansion": 1.6, "dilution": -2.0,
    # corporate events
    "acquisition": 1.4, "acquires": 1.4, "merger": 1.2, "takeover": 1.6,
    "partnership": 1.6, "contract": 1.4, "wins": 2.0, "won": 1.8,
    "awarded": 2.0, "approval": 2.2, "approved": 2.2,
    "launch": 1.2, "launches": 1.2, "breakthrough": 2.6, "milestone": 1.8,
    "layoffs": -2.0, "layoff": -2.0, "restructuring": -1.2,
    "bankruptcy": -3.6, "insolvency": -3.6,
    "default": -3.0, "defaults": -3.0, "delisting": -3.0, "delisted": -3.0,
    "halted": -2.4, "halt": -2.0, "suspension": -2.2, "suspended": -2.2,
    "recall": -2.6, "recalls": -2.6, "recalled": -2.6,
    "probe": -2.4, "investigation": -2.4, "investigated": -2.4,
    "subpoena": -2.6, "lawsuit": -2.4, "sued": -2.4, "sues": -2.0,
    "fined": -2.4, "penalty": -2.2, "fraud": -3.4, "scandal": -3.0,
    "breach": -2.6, "outage": -2.2,
    "warning": -2.0, "warns": -2.2, "warned": -2.0, "concerns": -1.6,
    "headwinds": -1.8, "tailwinds": 1.8, "uncertainty": -1.4,
    "resignation": -1.6, "resigns": -1.6, "ousted": -2.4,
    "offering": -1.2,
    # Direction words. Absent from stock VADER, yet "Is Down 7.6%" is the most
    # common way a headline states the only fact that matters.
    "down": -1.8, "up": 1.4, "higher": 1.8, "lower": -1.8,
    "upside": 1.8, "downside": -1.8, "upbeat": 2.0, "downbeat": -2.0,
    "record": 1.2, "deal": 0.8, "halving": -1.4, "doubling": 1.8,
    # hedges that VADER reads as positive but which only soften a claim
    "could": 0.0, "may": 0.0, "might": 0.0, "should": 0.0,
}

# VADER splits on whitespace, so a multi-word lexicon entry never matches.
# These phrases are collapsed to a single token first (see _collapse_phrases),
# which is the only way to score the cases where the phrase means the opposite
# of its parts: "cuts dividend" is bad news built from a positive noun.
PHRASE_LEXICON: dict[str, float] = {
    "raises guidance": 3.2, "raised guidance": 3.2, "guidance raised": 3.2,
    "lifts guidance": 3.2, "boosts guidance": 3.2, "hikes guidance": 3.0,
    "cuts guidance": -3.2, "cut guidance": -3.2, "guidance cut": -3.2,
    "lowers guidance": -3.2, "lowered guidance": -3.2, "slashes guidance": -3.4,
    "withdraws guidance": -3.4, "pulls guidance": -3.4,
    "cuts dividend": -3.2, "dividend cut": -3.2, "slashes dividend": -3.4,
    "suspends dividend": -3.4, "scraps dividend": -3.4,
    "raises dividend": 2.8, "hikes dividend": 2.8, "dividend hike": 2.8,
    "special dividend": 2.4,
    "price target raised": 2.8, "raises price target": 2.8,
    "price target cut": -2.8, "cuts price target": -2.8,
    "lowers price target": -2.8, "hikes price target": 2.8,
    "record high": 3.0, "all-time high": 3.2, "record low": -3.0,
    "all-time low": -3.2, "52-week high": 2.4, "52-week low": -2.4,
    "record revenue": 2.8, "record profit": 3.0, "record loss": -3.0,
    "bear market": -2.6, "bull market": 2.4,
    "job cuts": -2.2, "cuts jobs": -2.2, "mass layoffs": -2.8,
    "short seller": -2.6, "short-seller": -2.6, "short report": -2.6,
    "profit warning": -3.2, "profit taking": -1.0,
    "buy rating": 2.2, "sell rating": -2.2, "hold rating": 0.0,
    "beats estimates": 2.8, "misses estimates": -2.8,
    "tops estimates": 2.8, "misses expectations": -2.8,
    "beats expectations": 2.8, "raises concerns": -2.0,
    "steps down": -1.6, "chapter 11": -3.6, "going concern": -3.0,
    "stake sale": -1.2, "insider selling": -1.8, "insider buying": 1.8,
    "class action": -2.6, "sec probe": -3.0, "sec investigation": -3.0,
    "short squeeze": 2.0, "takeover bid": 2.2, "bidding war": 2.4,
    "deal collapses": -3.0, "deal falls apart": -3.0, "talks collapse": -2.8,
}

# Words VADER scores but which carry no market direction, so they add noise.
NEUTRALISE = ("share", "shares", "stock", "stocks", "market", "markets",
              "trading", "trade", "trades", "hold", "holds", "holding",
              "top", "best", "worst", "big", "great")

_lock = threading.Lock()
_vader: SentimentIntensityAnalyzer | None = None
_finbert = None
_finbert_failed = False


def _get_vader() -> SentimentIntensityAnalyzer:
    global _vader
    with _lock:
        if _vader is None:
            analyzer = SentimentIntensityAnalyzer()
            analyzer.lexicon.update(FINANCE_LEXICON)
            # Phrases enter the lexicon under their collapsed single-token form.
            analyzer.lexicon.update(
                {_collapsed(phrase): value for phrase, value in PHRASE_LEXICON.items()}
            )
            for word in NEUTRALISE:
                analyzer.lexicon.pop(word, None)
            _vader = analyzer
    return _vader


def _collapsed(phrase: str) -> str:
    return phrase.replace(" ", "_").replace("-", "_")


# Verb/noun pairs that routinely take a qualifier between them: "raises
# *earnings* guidance", "cuts its *full-year* guidance", "beats *analyst*
# estimates". Matching only the contiguous phrase missed all of those, so these
# families tolerate up to two intervening words. The rest stay strict, because
# loosening "short seller" or "profit taking" would invent signal.
_FLEXIBLE_HEADS = ("guidance", "dividend", "price target", "estimates", "expectations")

# Three, not two: a hyphenated qualifier ("its full-year guidance") counts as
# three word tokens once the hyphen is treated as a separator.
_GAP = r"[\s\-]+(?:\w+[\s\-]+){0,3}"


def _phrase_regex(phrase: str) -> str:
    escaped = re.escape(phrase).replace(r"\ ", r"[\s\-]+")
    if any(phrase.endswith(head) for head in _FLEXIBLE_HEADS) and " " in phrase:
        verb, _, head = phrase.rpartition(" ")
        return re.escape(verb).replace(r"\ ", r"[\s\-]+") + _GAP + re.escape(head)
    return escaped


# Longest first, so "cuts price target" wins over "price target".
_PHRASE_PATTERN = re.compile(
    "|".join(
        _phrase_regex(p) for p in sorted(PHRASE_LEXICON, key=len, reverse=True)
    ),
    re.IGNORECASE,
)

# Which lexicon entry a matched span maps to, once qualifiers are dropped.
_PHRASE_BY_WORDS = {
    tuple(phrase.replace("-", " ").split()): phrase for phrase in PHRASE_LEXICON
}


def _resolve_phrase(matched: str) -> str:
    """Map a matched span back to its lexicon key.

    "raises earnings guidance" must collapse to `raises_guidance`, not to a
    token nothing has a score for.
    """
    words = matched.lower().replace("-", " ").split()
    if tuple(words) in _PHRASE_BY_WORDS:
        return _collapsed(_PHRASE_BY_WORDS[tuple(words)])
    # Qualifiers were skipped: the first and last words carry the meaning.
    candidate = (words[0], words[-1])
    if candidate in _PHRASE_BY_WORDS:
        return _collapsed(_PHRASE_BY_WORDS[candidate])
    return _collapsed(" ".join(words))


def _collapse_phrases(text: str) -> str:
    """`cuts dividend` → `cuts_dividend`, so VADER can score it as one term."""
    if not text:
        return ""
    return _PHRASE_PATTERN.sub(lambda m: _resolve_phrase(m.group(0)), text)


def _get_finbert():
    """Load FinBERT once. Returns None if the extra isn't installed."""
    global _finbert, _finbert_failed
    if _finbert is not None or _finbert_failed:
        return _finbert
    with _lock:
        if _finbert is not None or _finbert_failed:
            return _finbert
        try:
            import torch
            from transformers import pipeline
            print("[sentiment] loading ProsusAI/finbert...")
            _finbert = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                truncation=True,
                max_length=512,
                batch_size=16,
                device=0 if torch.cuda.is_available() else -1,
            )
            print("[sentiment] finbert ready")
        except Exception as exc:
            _finbert_failed = True
            print(f"[sentiment] finbert unavailable ({type(exc).__name__}), using vader. "
                  "Install with: poetry install --extras finbert")
    return _finbert


def backend() -> str:
    """Which backend will actually be used, after availability checks."""
    if settings.SENTIMENT_BACKEND == "finbert" and _get_finbert() is not None:
        return "finbert"
    return "vader"


def score(text: str) -> float:
    return score_many([text])[0]


def score_many(texts: list[str]) -> list[float]:
    """Scores in [-1, 1]. Order matches the input."""
    if not texts:
        return []
    if backend() == "finbert":
        return _finbert_scores(texts)
    return _vader_scores(texts)


def _vader_scores(texts: list[str]) -> list[float]:
    analyzer = _get_vader()
    return [
        round(analyzer.polarity_scores(_collapse_phrases(t or ""))["compound"], 3)
        for t in texts
    ]


def _finbert_scores(texts: list[str]) -> list[float]:
    model = _get_finbert()
    try:
        results = model([t or "" for t in texts])
    except Exception as exc:
        print(f"[sentiment] finbert failed mid-batch ({exc}); falling back to vader")
        return _vader_scores(texts)

    analyzer = _get_vader()
    scores = []
    for text, result in zip(texts, results):
        label = (result.get("label") or "").lower()
        confidence = float(result.get("score") or 0)
        if label == "positive":
            scores.append(round(confidence, 3))
        elif label == "negative":
            scores.append(round(-confidence, 3))
        else:
            # FinBERT's "neutral" is often just low confidence. Let the tuned
            # lexicon break the tie when it feels strongly.
            fallback = analyzer.polarity_scores(text or "")["compound"]
            scores.append(round(fallback, 3) if abs(fallback) > 0.5 else 0.0)
    return scores


# ── DB-facing helpers ────────────────────────────────────────────────────

# The headline states the fact; descriptions are often syndication boilerplate
# ("find out what this means for your portfolio"), so they get a light vote
# rather than an equal one. Scoring them equally flipped
# "Rocket Lab Is Down 7.6%" positive.
_TITLE_WEIGHT = 0.75


def score_article(title: str, description: str | None = None) -> float:
    """Blended score for one article. Exposed for tests."""
    title_score = score_many([title or ""])[0]
    body = (description or "").strip()
    if not body:
        return title_score
    body_score = score_many([body[:600]])[0]
    return round(_TITLE_WEIGHT * title_score + (1 - _TITLE_WEIGHT) * body_score, 3)


def score_rows(rows: list[dict]) -> int:
    """Score rows of {id, title, description} and persist. Returns count."""
    if not rows:
        return 0
    scores = [score_article(r.get("title") or "", r.get("description")) for r in rows]
    return db.news.set_sentiment_many({r["id"]: s for r, s in zip(rows, scores)})


def score_news_ids(news_ids: list[UUID]) -> int:
    if not news_ids:
        return 0
    rows = [r for r in (db.news.get_news_by_id(i) for i in news_ids) if r]
    return score_rows(rows)


def score_unscored(limit: int = 500) -> int:
    """Catch-up pass for anything inserted while scoring was unavailable."""
    scored = score_rows(db.news.get_unscored(limit=limit))
    if scored:
        print(f"[sentiment] scored {scored} articles ({backend()})")
    return scored

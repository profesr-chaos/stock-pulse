"""Optional AI summaries via DeepSeek.

Entirely optional: without a DSEEK key every endpoint here reports that
summaries are unavailable, and the rest of the app is unaffected.

Summaries are cached hard and generated on request rather than for every
article on a schedule. The event layer (services/events.py) is the one
deliberate exception: it spends one call per stock per refresh, but only on a
refresh that actually inserted articles, and the churn filter is what keeps
that from being most refreshes. Pennies a day for a personal watchlist.
"""
from __future__ import annotations

import threading
from uuid import UUID

import db
import settings
from normalize import days_ago_iso, now_utc, parse_datetime

_client = None
_client_lock = threading.Lock()

ARTICLE_PROMPT = (
    "You are a concise financial news analyst. Given a news article's title, "
    "description and URL, write exactly two short paragraphs covering the key "
    "facts and what they mean for the stock. State only what the article "
    "supports. No disclaimers, no investment advice."
)

DIGEST_PROMPT = (
    "You are a concise financial news analyst. Given a list of recent "
    "headlines for one stock, write four short paragraphs: the dominant "
    "themes, the notable positives, the notable risks, and the overall tone. "
    "Refer to specific headlines. No disclaimers, no investment advice."
)


def available() -> bool:
    return settings.ai_enabled()


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            from openai import OpenAI
            _client = OpenAI(
                api_key=settings.DEEPSEEK_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                # A reasoning model is slow in wall-clock, not just in tokens:
                # a 60-article event prompt spends ~7,000 reasoning tokens and
                # takes ~57 seconds. The old 45s ceiling silently killed those
                # calls, so whole refreshes came back unjudged with nothing but
                # a timeout in the log. Every caller is a background job, so a
                # generous ceiling costs latency we are not waiting on.
                timeout=180.0,
            )
    return _client


# deepseek-v4-flash thinks before it answers, and `max_tokens` caps the
# reasoning and the answer *together*. How long it thinks varies run to run —
# the same trivial prompt spent 32 reasoning tokens on one call and blew a
# 320-token cap on the next, coming back with finish_reason='length' and empty
# content. A real 80-article event prompt spent 6,716. So a caller's max_tokens
# is treated as its *content* budget and the thinking gets headroom on top.
#
# Sized well above the worst case observed, because this is a ceiling and not a
# reservation: tokens that are not generated are not billed, so headroom costs
# nothing while a cap that is too tight costs the whole reply.
_REASONING_HEADROOM = 16000


def _complete(system: str, user: str, max_tokens: int,
              json_mode: bool = False) -> dict | None:
    """One completion, or None on any failure — callers degrade, never raise.

    `json_mode` constrains the reply to a JSON object. It makes the response
    parseable, not correct: callers must still validate what comes back.
    """
    extra = {"response_format": {"type": "json_object"}} if json_mode else {}
    try:
        response = _get_client().chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens + _REASONING_HEADROOM,
            **extra,
        )
    except Exception as exc:
        print(f"[ai] request failed: {type(exc).__name__}: {exc}")
        return None

    choice = (response.choices or [None])[0]
    text = (choice.message.content or "").strip() if choice else ""
    if not text:
        # Worth saying out loud: an empty reply reads to every caller as "the
        # AI is down", and the usual cause is the token budget, not the API.
        reason = getattr(choice, "finish_reason", "?") if choice else "no choices"
        print(f"[ai] empty response (finish_reason={reason})")
        return None

    usage = response.usage
    return {
        "text": text,
        "tokens_in": getattr(usage, "prompt_tokens", 0) or 0,
        "tokens_out": getattr(usage, "completion_tokens", 0) or 0,
    }


# ── Single article ───────────────────────────────────────────────────────

def summarise_article(news_id: UUID) -> dict | None:
    """Summarise one article, caching the result on its row."""
    if not available():
        return None

    article = db.news.get_news_by_id(news_id)
    if not article:
        return None
    if article.get("ai_summary"):
        return {"id": news_id, "ai_summary": article["ai_summary"], "cached": True}

    if not (article.get("title") or article.get("description")):
        return None

    user = (
        f"Stock: {article['short_name']}\n"
        f"Title: {article['title']}\n"
        f"Description: {article.get('description') or 'None provided'}\n"
        f"URL: {article['url']}\n\n"
        "Summarise this article in two paragraphs."
    )
    result = _complete(ARTICLE_PROMPT, user, max_tokens=320)
    if not result:
        return None

    db.news.update_news(news_id, ai_summary=result["text"])
    return {"id": news_id, "ai_summary": result["text"], "cached": False}


# ── Whole-stock digest ───────────────────────────────────────────────────

def summarise_stock(short_name: str, days: int = 7, max_age_hours: int = 24) -> dict | None:
    """Digest of a stock's recent coverage, cached for a day.

    Re-uses the cached digest unless it has expired *or* new articles have
    arrived since it was written — a summary that predates today's news is
    exactly the summary you don't want.
    """
    if not available():
        return None

    cached = db.summaries.latest_summary(short_name)
    if cached and _still_fresh(cached, short_name, max_age_hours):
        return {
            "symbol": short_name,
            "ai_summary": cached["ai_summary"],
            "article_count": cached.get("article_count") or 0,
            "cached": True,
        }

    articles = db.news.get_news([short_name], since=days_ago_iso(days), limit=60)
    if not articles:
        return None

    digest = "\n".join(
        f"- [{a['publish_time'][:10]}] {a['title']}"
        + (f" — {a['description'][:180]}" if a.get("description") else "")
        for a in articles
    )
    user = (
        f"Stock: {short_name}\nHeadlines from the last {days} days "
        f"({len(articles)} articles):\n\n{digest}"
    )
    result = _complete(DIGEST_PROMPT, user, max_tokens=520)
    if not result:
        return None

    db.summaries.insert_summary(
        short_name,
        result["text"],
        tokens_total=result["tokens_in"] + result["tokens_out"],
        days=days,
        article_count=len(articles),
    )
    return {
        "symbol": short_name,
        "ai_summary": result["text"],
        "article_count": len(articles),
        "cached": False,
    }


def _still_fresh(cached: dict, short_name: str, max_age_hours: int) -> bool:
    created = parse_datetime(cached.get("created_at"))
    if not created:
        return False
    if (now_utc() - created).total_seconds() > max_age_hours * 3600:
        return False

    # Any article newer than the summary makes it stale.
    newer = db.news.get_news([short_name], since=cached["created_at"], limit=1)
    return not newer

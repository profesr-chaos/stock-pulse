"""Runtime feature flags, set from the UI rather than the environment.

Env vars in settings.py answer "what is this deployment wired up to" — a DSN, a
port, an API key. This answers "what does the user want switched on right now",
which is a different question with a different lifetime: it changes while the
app is running and must survive a restart.

Two independent flags, deliberately not one:

    llm_scraping   spend a call per refresh grading new articles for impact
    ai_summaries   spend a call when someone asks for a summary

Turning one off must never turn the other off. They are the same key and the
same provider, but one is a background cost the user never asked for and the
other is an explicit click — someone who wants to stop the silent spend still
wants the button to work.
"""
from __future__ import annotations

from .connection import get_connection

LLM_SCRAPING = "llm_scraping"
AI_SUMMARIES = "ai_summaries"

# Both default on: an existing install that has a key keeps behaving the way it
# did before the flags existed.
DEFAULTS = {LLM_SCRAPING: True, AI_SUMMARIES: True}


def get_flag(key: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_config WHERE key = %s", (key,)
        ).fetchone()
    if row is None:
        return DEFAULTS.get(key, True)
    return row["value"] == "1"


def set_flag(key: str, value: bool) -> bool:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO app_config (key, value) VALUES (%s, %s)"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (key, "1" if value else "0"),
        )
    return value


def get_all() -> dict[str, bool]:
    """Every flag, defaults filled in for the ones never written."""
    with get_connection() as conn:
        stored = {r["key"]: r["value"] == "1"
                  for r in conn.execute("SELECT key, value FROM app_config")}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}

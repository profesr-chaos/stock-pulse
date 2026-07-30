"""All configuration in one place, env-driven, with defaults that work out of the box.

Single-user local tool: no auth, no paid API keys required. The only optional
keys are DSEEK (DeepSeek, for AI summaries) and 212pk/212sk (Trading212, only
needed to refresh the instrument catalogue — 15k instruments are already cached
in the DB).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# ── Storage ──────────────────────────────────────────────────────────────
# A directory, not a bare file: WAL mode writes sibling -wal/-shm files.
DB_PATH = Path(os.getenv("STOCKY_DB") or ROOT / "data" / "stocky.db")

# ── API ──────────────────────────────────────────────────────────────────
# Loopback only. This is a personal tool with no auth; it must not be
# reachable from the network. Override deliberately if you ever need to.
HOST = os.getenv("STOCKY_HOST", "127.0.0.1")
PORT = _int("STOCKY_PORT", 5000)

# Explicit allow-list. `*` plus credentials is rejected by browsers anyway,
# and a wildcard on an unauthenticated local API lets any page you visit
# read your watchlist.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "STOCKY_CORS_ORIGINS",
        "http://localhost:8080,http://127.0.0.1:8080,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

# ── Data freshness ───────────────────────────────────────────────────────
BACKFILL_DAYS = _int("STOCKY_BACKFILL_DAYS", 30)      # history pulled for a new follow
PRICE_REFRESH_MINUTES = _int("STOCKY_PRICE_REFRESH_MINUTES", 60)
NEWS_REFRESH_MINUTES = _int("STOCKY_NEWS_REFRESH_MINUTES", 60)
QUOTE_STALE_MINUTES = _int("STOCKY_QUOTE_STALE_MINUTES", 60)   # serve cached quote under this age
NEWS_RETENTION_DAYS = _int("STOCKY_NEWS_RETENTION_DAYS", 120)

# ── Scraping ─────────────────────────────────────────────────────────────
SCRAPE_TIMEOUT = _float("STOCKY_SCRAPE_TIMEOUT", 12.0)
SCRAPE_MAX_RETRIES = _int("STOCKY_SCRAPE_MAX_RETRIES", 3)
SCRAPE_CONCURRENCY = _int("STOCKY_SCRAPE_CONCURRENCY", 8)      # total in-flight requests
SCRAPE_CACHE_TTL = _float("STOCKY_SCRAPE_CACHE_TTL", 300.0)    # seconds
FETCH_ARTICLE_IMAGES = _flag("STOCKY_FETCH_ARTICLE_IMAGES", True)
IMAGE_FETCH_LIMIT = _int("STOCKY_IMAGE_FETCH_LIMIT", 12)       # per stock per refresh

# ── Sentiment ────────────────────────────────────────────────────────────
# "vader"   → finance-tuned VADER, no torch, instant (default)
# "finbert" → ProsusAI/finbert, needs `--extras finbert`, much heavier
SENTIMENT_BACKEND = os.getenv("STOCKY_SENTIMENT", "vader").strip().lower()

# ── Optional third-party keys ────────────────────────────────────────────
DEEPSEEK_KEY = os.getenv("DSEEK") or None
DEEPSEEK_BASE_URL = os.getenv("STOCKY_DEEPSEEK_URL", "https://api.deepseek.com")
T212_KEY = os.getenv("212pk") or None
T212_SECRET = os.getenv("212sk") or None
T212_INSTRUMENTS_URL = os.getenv(
    "STOCKY_T212_URL",
    "https://demo.trading212.com/api/v0/equity/metadata/instruments",
)


def ai_enabled() -> bool:
    return bool(DEEPSEEK_KEY)


def t212_enabled() -> bool:
    return bool(T212_KEY and T212_SECRET)

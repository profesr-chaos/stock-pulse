"""The LLM is optional equipment.

Stocky is a scraper first. Everything here defends one claim: **a refresh
stores the same articles whether or not there is a working LLM behind it.**
Losing the model costs the feed its impact tiers and its event rows. It must
never cost it an article.

Three ways the LLM can be absent, and all three have to behave identically:

    no key at all      settings.DEEPSEEK_KEY is None
    a rejected key     the provider 401s — the expensive one, see below
    switched off       the user turned the flag off in the UI

The rejected key is the case worth the most attention. `ai_enabled()` only
asks whether the string is non-empty, so before the circuit breaker an expired
key meant every stock in every hourly refresh paid a full round trip to be told
401 again. Nothing broke and nothing logged loudly; the refresh just got slower
and slower as the watchlist grew.
"""
from __future__ import annotations

import json

import pytest

import db
import settings
from normalize import now_utc, to_iso
from services import ai_service, events
from services import news as news_service


# ── Fixtures and doubles ─────────────────────────────────────────────────

_HEADLINES = [
    "Apple beats Q3 estimates as iPhone revenue tops forecasts",
    "Apple recalls 200,000 chargers over an overheating risk",
    "Morgan Stanley raises its Apple price target to $310",
    "Apple opens a second manufacturing site in Bengaluru",
]


def _raw(*urls: str, start: int = 0) -> list[dict]:
    """Scraped-article dicts that survive the relevance filter for AAPL.

    Distinct headlines, not variations: near-identical titles get collapsed by
    clustering and the test would be measuring dedup instead of the LLM. `start`
    exists for the same reason — a second refresh in one test has to bring a
    genuinely different story or dedup eats it before the LLM is consulted.
    """
    return [{
        "title": _HEADLINES[(start + n) % len(_HEADLINES)],
        "url": url,
        "published_at": now_utc(),
        "source": "Reuters",
        "source_domain": "reuters.com",
        "source_type": "GOOGLE_NEWS",
    } for n, url in enumerate(urls)]


@pytest.fixture
def scrape(monkeypatch):
    """Stub the network out of refresh(), leaving dedup, storage and events real."""
    def install(raw: list[dict]) -> None:
        monkeypatch.setattr(news_service, "collect", lambda *a, **kw: raw)
        monkeypatch.setattr(news_service.sentiment_service, "score_news_ids", lambda *a: None)
        monkeypatch.setattr(news_service.images, "backfill_images", lambda *a: None)
    return install


class _Counter:
    """Stands in for ai_service._complete and counts what it cost."""

    def __init__(self, reply=None):
        self.calls = 0
        self.reply = reply

    def __call__(self, system, user, max_tokens, json_mode=False):
        self.calls += 1
        return self.reply


def _events_reply(*headlines: str) -> dict:
    payload = {"events": [{
        "headline": h,
        "why_it_matters": "It moves the business.",
        "previously_known": None,
        "impact": "high",
        "article_numbers": [1],
    } for h in headlines]}
    return {"text": json.dumps(payload), "tokens_in": 100, "tokens_out": 50}


def _rejecting_client(status_code: int):
    """A client whose every call fails the way the provider fails it."""
    error = Exception(f"HTTP {status_code}")
    error.status_code = status_code

    class _Completions:
        def create(self, **kwargs):
            raise error

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


@pytest.fixture
def live_key(monkeypatch):
    """A key that is present, so only the flags and the provider decide."""
    monkeypatch.setattr(settings, "DEEPSEEK_KEY", "sk-test-key")
    ai_service.reset_key_state()


@pytest.fixture
def article_id(temp_db):
    return db.news.insert_news_many([{
        "short_name": "AAPL",
        "title": "Apple beats Q3 estimates as iPhone revenue tops forecasts",
        "title_key": "apple-q3",
        "url": "https://reuters.com/AAPL/q3",
        "url_hash": "hash-aapl-q3",
        "source": "Reuters",
        "source_domain": "reuters.com",
        "source_type": "GOOGLE_NEWS",
        "publish_time": to_iso(now_utc()),
    }])[0]


# ── The headline claim ───────────────────────────────────────────────────

class TestScrapingSurvivesWithoutAnLLM:
    """Same articles stored, whatever the LLM is doing."""

    def test_no_key_still_stores_every_article(self, stocked_db, scrape, monkeypatch):
        monkeypatch.setattr(settings, "DEEPSEEK_KEY", None)
        ai_service.reset_key_state()
        scrape(_raw("https://reuters.com/a", "https://reuters.com/b"))

        result = news_service.refresh("AAPL", days=2)

        assert result["inserted"] == 2
        assert result["found"] == 2

    def test_no_key_costs_no_calls(self, stocked_db, scrape, monkeypatch):
        monkeypatch.setattr(settings, "DEEPSEEK_KEY", None)
        ai_service.reset_key_state()
        counter = _Counter()
        monkeypatch.setattr(ai_service, "_complete", counter)
        scrape(_raw("https://reuters.com/a"))

        news_service.refresh("AAPL", days=2)
        assert counter.calls == 0

    def test_switched_off_still_stores_every_article(self, stocked_db, scrape,
                                                     live_key, monkeypatch):
        db.flags.set_flag(db.flags.LLM_SCRAPING, False)
        counter = _Counter(_events_reply("Apple recalls chargers"))
        monkeypatch.setattr(ai_service, "_complete", counter)
        scrape(_raw("https://reuters.com/a", "https://reuters.com/b"))

        result = news_service.refresh("AAPL", days=2)

        assert result["inserted"] == 2
        assert counter.calls == 0
        assert db.events.get_events(["AAPL"]) == []

    def test_rejected_key_still_stores_every_article(self, stocked_db, scrape,
                                                     live_key, monkeypatch):
        monkeypatch.setattr(ai_service, "_get_client", lambda: _rejecting_client(401))
        scrape(_raw("https://reuters.com/a", "https://reuters.com/b"))

        result = news_service.refresh("AAPL", days=2)

        assert result["inserted"] == 2

    @pytest.mark.parametrize("mode", ["no_key", "switched_off", "rejected"])
    def test_every_off_mode_stores_identically(self, stocked_db, scrape, monkeypatch, mode):
        """The three ways to be without an LLM must not differ in what lands."""
        if mode == "no_key":
            monkeypatch.setattr(settings, "DEEPSEEK_KEY", None)
            ai_service.reset_key_state()
        elif mode == "switched_off":
            monkeypatch.setattr(settings, "DEEPSEEK_KEY", "sk-test-key")
            ai_service.reset_key_state()
            db.flags.set_flag(db.flags.LLM_SCRAPING, False)
        else:
            monkeypatch.setattr(settings, "DEEPSEEK_KEY", "sk-test-key")
            ai_service.reset_key_state()
            monkeypatch.setattr(ai_service, "_get_client", lambda: _rejecting_client(401))

        scrape(_raw("https://reuters.com/a", "https://reuters.com/b", "https://reuters.com/c"))
        result = news_service.refresh("AAPL", days=2)

        assert result["inserted"] == 3
        stored = db.news.get_news(["AAPL"])
        assert len(stored) == 3
        # Ungraded, not graded 'low'. A later refresh with the LLM back on can
        # still judge these; a 'low' would mean "we looked and found nothing".
        assert all(a["impact"] is None for a in stored)

    def test_grading_on_still_grades(self, stocked_db, scrape, live_key, monkeypatch):
        """The control: with everything on, the tiers still land."""
        counter = _Counter(_events_reply("Apple recalls 200,000 chargers"))
        monkeypatch.setattr(ai_service, "_complete", counter)
        scrape(_raw("https://reuters.com/a"))

        result = news_service.refresh("AAPL", days=2)

        assert result["inserted"] == 1
        assert counter.calls == 1
        assert [e["headline"] for e in db.events.get_events(["AAPL"])] == [
            "Apple recalls 200,000 chargers"
        ]
        assert db.news.get_news(["AAPL"])[0]["impact"] == "high"


# ── The expired key ──────────────────────────────────────────────────────

class TestRejectedKeyStopsCostingTime:
    """A 401 is permanent until someone fixes the key. Retrying it every
    refresh is what made an expired key expensive rather than merely useless."""

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_failure_disables_the_llm(self, temp_db, live_key, monkeypatch, status):
        monkeypatch.setattr(ai_service, "_get_client", lambda: _rejecting_client(status))
        assert ai_service.key_usable() is True

        assert ai_service._complete("s", "u", max_tokens=10) is None

        assert ai_service.key_usable() is False
        assert ai_service.key_rejected() is True

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_retryable_failures_do_not_disable_it(self, temp_db, live_key,
                                                  monkeypatch, status):
        """Rate limits and outages pass. Latching on those would take the
        feature down for the rest of the day over a transient blip."""
        monkeypatch.setattr(ai_service, "_get_client", lambda: _rejecting_client(status))

        assert ai_service._complete("s", "u", max_tokens=10) is None

        assert ai_service.key_usable() is True
        assert ai_service.key_rejected() is False

    def test_a_failure_with_no_status_does_not_disable_it(self, temp_db, live_key,
                                                          monkeypatch):
        """A socket timeout carries no status_code — it must not read as auth."""
        class _Completions:
            def create(self, **kwargs):
                raise TimeoutError("read timed out")

        client = type("C", (), {"chat": type("Ch", (), {"completions": _Completions()})()})()
        monkeypatch.setattr(ai_service, "_get_client", lambda: client)

        assert ai_service._complete("s", "u", max_tokens=10) is None
        assert ai_service.key_usable() is True

    def test_the_second_refresh_stops_calling_out(self, stocked_db, scrape,
                                                  live_key, monkeypatch):
        """The point of the breaker: one wasted round trip, not one per stock
        per refresh forever."""
        attempts = {"n": 0}

        class _Completions:
            def create(self, **kwargs):
                attempts["n"] += 1
                error = Exception("HTTP 401")
                error.status_code = 401
                raise error

        client = type("C", (), {"chat": type("Ch", (), {"completions": _Completions()})()})()
        monkeypatch.setattr(ai_service, "_get_client", lambda: client)

        scrape(_raw("https://reuters.com/a"))
        news_service.refresh("AAPL", days=2)
        scrape(_raw("https://reuters.com/b", start=1))
        news_service.refresh("AAPL", days=2)

        assert attempts["n"] == 1
        # ...and both refreshes still stored their article.
        assert len(db.news.get_news(["AAPL"])) == 2

    def test_reset_re_arms_after_the_key_is_fixed(self, temp_db, live_key, monkeypatch):
        monkeypatch.setattr(ai_service, "_get_client", lambda: _rejecting_client(401))
        ai_service._complete("s", "u", max_tokens=10)
        assert ai_service.key_usable() is False

        ai_service.reset_key_state()
        assert ai_service.key_usable() is True


# ── The two flags are independent ────────────────────────────────────────

class TestTogglesDoNotLeakIntoEachOther:
    """`switch off LLM scraping` must switch off *only* scraping."""

    def test_scraping_off_leaves_summaries_working(self, temp_db, article_id,
                                                   live_key, monkeypatch):
        db.flags.set_flag(db.flags.LLM_SCRAPING, False)
        monkeypatch.setattr(
            ai_service, "_complete",
            lambda *a, **kw: {"text": "A summary.", "tokens_in": 5, "tokens_out": 5},
        )

        assert events.enabled() is False
        assert ai_service.available() is True
        assert ai_service.summarise_article(article_id)["ai_summary"] == "A summary."

    def test_summaries_off_leaves_grading_working(self, temp_db, live_key):
        db.flags.set_flag(db.flags.AI_SUMMARIES, False)

        assert ai_service.available() is False
        assert events.enabled() is True

    def test_summaries_off_refuses_to_summarise(self, temp_db, article_id,
                                                live_key, monkeypatch):
        db.flags.set_flag(db.flags.AI_SUMMARIES, False)
        counter = _Counter({"text": "x", "tokens_in": 1, "tokens_out": 1})
        monkeypatch.setattr(ai_service, "_complete", counter)

        assert ai_service.summarise_article(article_id) is None
        assert counter.calls == 0

    def test_both_default_on(self, temp_db):
        assert db.flags.get_all() == {
            db.flags.LLM_SCRAPING: True,
            db.flags.AI_SUMMARIES: True,
        }

    def test_a_flag_survives_being_read_back(self, temp_db):
        db.flags.set_flag(db.flags.LLM_SCRAPING, False)
        assert db.flags.get_flag(db.flags.LLM_SCRAPING) is False
        assert db.flags.get_flag(db.flags.AI_SUMMARIES) is True

        db.flags.set_flag(db.flags.LLM_SCRAPING, True)
        assert db.flags.get_flag(db.flags.LLM_SCRAPING) is True

    def test_no_key_makes_both_inert_without_clearing_the_flags(self, temp_db, monkeypatch):
        """The user's preference is remembered even while it cannot take
        effect — adding a key later must not also need re-ticking the boxes."""
        monkeypatch.setattr(settings, "DEEPSEEK_KEY", None)
        ai_service.reset_key_state()

        assert events.enabled() is False
        assert ai_service.available() is False
        assert db.flags.get_flag(db.flags.LLM_SCRAPING) is True


# ── The API the UI drives ────────────────────────────────────────────────

class TestConfigApi:
    def test_defaults(self, client, live_key):
        body = client.get("/config").json()
        assert body["llmScraping"] is True
        assert body["aiSummaries"] is True
        assert body["keyPresent"] is True
        assert body["keyRejected"] is False
        assert body["scrapingGradesImpact"] is True

    def test_put_one_flag_leaves_the_other_alone(self, client, live_key):
        body = client.put("/config", json={"llmScraping": False}).json()

        assert body["llmScraping"] is False
        assert body["aiSummaries"] is True
        assert body["summariesAvailable"] is True
        assert body["scrapingGradesImpact"] is False

    def test_put_persists(self, client, live_key):
        client.put("/config", json={"llmScraping": False})
        assert client.get("/config").json()["llmScraping"] is False

        client.put("/config", json={"llmScraping": True})
        assert client.get("/config").json()["llmScraping"] is True

    def test_put_both_at_once(self, client, live_key):
        body = client.put(
            "/config", json={"llmScraping": False, "aiSummaries": False}
        ).json()
        assert (body["llmScraping"], body["aiSummaries"]) == (False, False)

    def test_empty_put_changes_nothing(self, client, live_key):
        client.put("/config", json={"llmScraping": False})
        body = client.put("/config", json={}).json()
        assert body["llmScraping"] is False

    def test_effective_state_reflects_a_missing_key(self, client, monkeypatch):
        monkeypatch.setattr(settings, "DEEPSEEK_KEY", None)
        ai_service.reset_key_state()

        body = client.get("/config").json()
        assert body["keyPresent"] is False
        # Wanted on, cannot run — the distinction the UI needs to explain itself.
        assert body["llmScraping"] is True
        assert body["scrapingGradesImpact"] is False
        assert body["summariesAvailable"] is False

    def test_health_reports_the_grading_state(self, client, live_key):
        assert client.get("/health").json()["impact_grading"] == "enabled"

        client.put("/config", json={"llmScraping": False})
        assert client.get("/health").json()["impact_grading"] == "disabled"

    def test_health_distinguishes_a_rejected_key(self, client, live_key, monkeypatch):
        monkeypatch.setattr(ai_service, "_get_client", lambda: _rejecting_client(401))
        ai_service._complete("s", "u", max_tokens=10)

        assert client.get("/health").json()["ai_summaries"] == "disabled (key rejected)"

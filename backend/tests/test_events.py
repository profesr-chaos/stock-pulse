"""Event detection.

The LLM is stubbed at `ai_service._complete`, so these tests are about the two
things that actually matter: that a refresh can never be broken by the model,
and that we only pay for a call when there is something new to judge. Everything
else runs for real against the test database.
"""
from __future__ import annotations

import json

import pytest

import db
from normalize import days_ago_iso, now_utc, to_iso
from services import ai_service, events
from services import news as news_service


def _articles(short_name: str = "AAPL", count: int = 3) -> list:
    """Store `count` articles and return their ids, in order."""
    return db.news.insert_news_many([
        {
            "short_name": short_name,
            "title": f"Apple story number {n} about something happening",
            "title_key": f"apple-story-{n}",
            "url": f"https://reuters.com/{short_name}/{n}",
            "url_hash": f"hash-{short_name}-{n}",
            "source": "Reuters",
            "source_domain": "reuters.com",
            "source_type": "GOOGLE_NEWS",
            "publish_time": to_iso(now_utc()),
        }
        for n in range(1, count + 1)
    ])


def _reply(payload, tokens_in: int = 100, tokens_out: int = 50) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"text": text, "tokens_in": tokens_in, "tokens_out": tokens_out}


# Distinct stories, not variations: near-identical titles would be collapsed by
# clustering before they ever reached the event layer.
_HEADLINES = [
    "Apple beats Q3 estimates as iPhone revenue tops forecasts",
    "Apple recalls 200,000 chargers over an overheating risk",
    "Morgan Stanley raises its Apple price target to $310",
    "Apple opens a second manufacturing site in Bengaluru",
    "Tim Cook sells 120,000 Apple shares under a 10b5-1 plan",
]


def _raw(*urls: str) -> list[dict]:
    """Scraped-article dicts that survive the relevance filter for AAPL."""
    return [{
        "title": _HEADLINES[n % len(_HEADLINES)],
        "url": url,
        "published_at": now_utc(),
        "source": "Reuters",
        "source_domain": "reuters.com",
        "source_type": "GOOGLE_NEWS",
    } for n, url in enumerate(urls)]


def _stub_scrape(monkeypatch, raw: list[dict]) -> None:
    """Everything in refresh() except dedup, storage and event detection."""
    monkeypatch.setattr(news_service, "collect", lambda *a, **kw: raw)
    monkeypatch.setattr(news_service.sentiment_service, "score_news_ids", lambda *a: None)
    monkeypatch.setattr(news_service.images, "backfill_images", lambda *a: None)


class _Stub:
    """Stands in for the LLM: counts calls, records prompts, returns `reply`."""

    def __init__(self):
        self.calls = 0
        self.prompts: list[str] = []
        self.reply: dict | None = None
        # Set instead of `reply` to vary the answer per call, e.g. to fail the
        # first page and succeed on the second.
        self.reply_for_call = None

    def __call__(self, system, user, max_tokens, json_mode=False):
        self.calls += 1
        self.prompts.append(user)
        if self.reply_for_call is not None:
            return self.reply_for_call(self.calls)
        return self.reply


@pytest.fixture
def stub(monkeypatch):
    stub = _Stub()
    monkeypatch.setattr(ai_service, "_complete", stub)
    monkeypatch.setattr(ai_service, "available", lambda: True)
    return stub


class TestDetect:
    def test_valid_response_inserts_events_with_mapped_article_ids(self, temp_db, stub):
        ids = _articles(count=3)
        stub.reply = _reply({"events": [{
            "headline": "Apple recalls 200,000 chargers",
            "why_it_matters": "First hardware recall since 2023 and it hits the accessory line.",
            "previously_known": None,
            "impact": "high",
            "article_numbers": [1, 3],
        }]})

        written = events.detect("AAPL", ids)

        assert len(written) == 1
        stored = db.events.get_events(["AAPL"])
        assert len(stored) == 1
        assert stored[0]["headline"] == "Apple recalls 200,000 chargers"
        assert stored[0]["impact"] == "high"
        # Numbers are 1-based indexes into the batch, in the order passed in.
        assert stored[0]["news_ids"] == [ids[0], ids[2]]
        assert stored[0]["tokens_total"] == 150

    def test_claimed_articles_take_the_event_tier_and_the_rest_are_low(self, temp_db, stub):
        ids = _articles(count=3)
        stub.reply = _reply({"events": [{
            "headline": "Apple recalls 200,000 chargers",
            "why_it_matters": "Hits the accessory line.",
            "previously_known": None,
            "impact": "high",
            "article_numbers": [2],
        }]})

        events.detect("AAPL", ids)

        impacts = [db.news.get_news_by_id(i)["impact"] for i in ids]
        assert impacts == ["low", "high", "low"]

    def test_no_events_marks_the_whole_batch_low(self, temp_db, stub):
        """The expected common answer: coverage happened, nothing new did."""
        ids = _articles(count=2)
        stub.reply = _reply({"events": []})

        assert events.detect("AAPL", ids) == []
        assert db.events.get_events(["AAPL"]) == []
        assert [db.news.get_news_by_id(i)["impact"] for i in ids] == ["low", "low"]

    def test_an_article_backing_two_events_takes_the_higher_tier(self, temp_db, stub):
        ids = _articles(count=2)
        stub.reply = _reply({"events": [
            {"headline": "A", "why_it_matters": "x", "previously_known": None,
             "impact": "low", "article_numbers": [1]},
            {"headline": "B", "why_it_matters": "y", "previously_known": None,
             "impact": "high", "article_numbers": [1, 2]},
        ]})

        events.detect("AAPL", ids)
        assert db.news.get_news_by_id(ids[0])["impact"] == "high"

    def test_prior_coverage_excludes_the_new_batch(self, temp_db, stub):
        """The prior is what the investor already knew — the articles being
        judged are not part of it, or the model is told the news is old news."""
        _articles(count=1)
        new = db.news.insert_news_many([{
            "short_name": "AAPL", "title": "Apple recalls 200,000 chargers",
            "title_key": "recall", "url": "https://reuters.com/recall",
            "url_hash": "hash-recall", "source": "Reuters",
            "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
            "publish_time": to_iso(now_utc()),
        }])
        stub.reply = _reply({"events": []})

        events.detect("AAPL", new)

        prompt = stub.prompts[0]
        prior, _, batch = prompt.partition("NEW ARTICLES")
        assert "Apple story number 1" in prior
        assert "Apple recalls 200,000 chargers" not in prior
        assert "Apple recalls 200,000 chargers" in batch


class TestDetectCannotBreakARefresh:
    """Every one of these must be zero events and no exception."""

    @pytest.mark.parametrize("text", [
        "not json at all",
        "",
        "{",
        '{"events": "nope"}',
        '{"nothing": []}',
        '["events"]',
        '{"events": [{"headline": "x"}]}',                      # missing fields
        '{"events": [{"headline": "x", "why_it_matters": "y", '
        '"impact": "catastrophic", "article_numbers": [1]}]}',  # unknown tier
        '{"events": [{"headline": "x", "why_it_matters": "y", '
        '"impact": "high", "article_numbers": [99]}]}',         # out of range
        '{"events": [{"headline": "x", "why_it_matters": "y", '
        '"impact": "high", "article_numbers": []}]}',
        '{"events": [{"headline": "x", "why_it_matters": "y", '
        '"impact": "high", "article_numbers": "1"}]}',
        '{"events": ["a string where an object goes"]}',
    ])
    def test_malformed_responses_insert_nothing(self, temp_db, stub, text):
        ids = _articles(count=2)
        stub.reply = _reply(text)

        assert events.detect("AAPL", ids) == []
        assert db.events.get_events(["AAPL"]) == []

    def test_a_dead_llm_leaves_articles_unjudged_rather_than_low(self, temp_db, stub):
        """None is not 'nothing new' — we never got an opinion, so impact stays
        NULL and a later refresh can still judge it."""
        ids = _articles(count=2)
        stub.reply = None

        assert events.detect("AAPL", ids) == []
        assert [db.news.get_news_by_id(i)["impact"] for i in ids] == [None, None]

    def test_one_malformed_event_does_not_discard_a_valid_one(self, temp_db, stub):
        ids = _articles(count=2)
        stub.reply = _reply({"events": [
            {"headline": "bad", "impact": "high"},
            {"headline": "Apple recalls chargers", "why_it_matters": "big",
             "previously_known": None, "impact": "high", "article_numbers": [1]},
        ]})

        written = events.detect("AAPL", ids)
        assert [e["headline"] for e in written] == ["Apple recalls chargers"]

    def test_no_api_key_is_a_no_op(self, temp_db, stub, monkeypatch):
        monkeypatch.setattr(ai_service, "available", lambda: False)
        ids = _articles(count=2)

        assert events.detect("AAPL", ids) == []
        assert stub.calls == 0
        assert [db.news.get_news_by_id(i)["impact"] for i in ids] == [None, None]

    def test_a_raising_detector_does_not_fail_the_refresh(self, stocked_db, monkeypatch):
        """detect() is allowed to blow up — refresh() contains it, the way it
        contains a scraper source going down."""
        def boom(*args, **kwargs):
            raise RuntimeError("deepseek is on fire")

        _stub_scrape(monkeypatch, _raw("https://reuters.com/containment"))
        monkeypatch.setattr(events, "detect", boom)

        result = news_service.refresh("AAPL", days=2)
        assert result["inserted"] == 1


class TestCallBudget:
    """At most one call per stock per refresh, and none when there is nothing
    to judge — this is the whole cost story."""

    def test_one_call_per_refresh_however_many_articles(self, stocked_db, stub, monkeypatch):
        stub.reply = _reply({"events": []})
        _stub_scrape(monkeypatch, _raw(*[f"https://reuters.com/x{n}" for n in range(5)]))

        result = news_service.refresh("AAPL", days=2)
        assert result["inserted"] == 5
        assert stub.calls == 1

    def test_a_batch_larger_than_one_call_is_paged_not_truncated(self, temp_db, stub):
        """Every inserted article must come out with a tier. Capping the batch
        instead of paging it left the overflow permanently NULL — which reads
        in the feed as "not judged yet" forever."""
        ids = _articles(count=events._BATCH_SIZE + 25)
        stub.reply = _reply({"events": []})

        events.detect("AAPL", ids)

        assert stub.calls == 2
        assert all(db.news.get_news_by_id(i)["impact"] == "low" for i in ids)

    def test_one_failed_page_does_not_cost_the_others_their_tier(self, temp_db, stub):
        """A timeout on one call is the failure that actually happened in
        production; it must not spread to articles another call covered."""
        replies = [None, _reply({"events": []})]
        stub.reply_for_call = lambda n: replies[n - 1]

        ids = _articles(count=events._BATCH_SIZE + 10)
        events.detect("AAPL", ids)

        impacts = [db.news.get_news_by_id(i)["impact"] for i in ids]
        # Page one timed out and stays unjudged; page two still got its tier.
        assert impacts[:events._BATCH_SIZE] == [None] * events._BATCH_SIZE
        assert impacts[events._BATCH_SIZE:] == ["low"] * 10

    def test_no_call_when_nothing_was_inserted(self, stocked_db, stub, monkeypatch):
        _stub_scrape(monkeypatch, [])
        news_service.refresh("AAPL", days=2)
        assert stub.calls == 0

    def test_no_call_when_every_article_was_already_stored(self, stocked_db, stub, monkeypatch):
        """A refresh that finds only what it already has must cost nothing."""
        stub.reply = _reply({"events": []})
        _stub_scrape(monkeypatch, _raw("https://reuters.com/same"))

        news_service.refresh("AAPL", days=2)
        news_service.refresh("AAPL", days=2)
        assert stub.calls == 1

    def test_backfill_never_judges(self, stocked_db, stub, monkeypatch):
        """A month of history is not new events."""
        _stub_scrape(monkeypatch, _raw("https://reuters.com/backfill"))

        result = news_service.backfill("AAPL", days=30)
        assert result["inserted"] == 1
        assert stub.calls == 0

    def test_detect_events_false_skips_the_call(self, stocked_db, stub, monkeypatch):
        _stub_scrape(monkeypatch, _raw("https://reuters.com/y"))

        news_service.refresh("AAPL", days=2, detect_events=False)
        assert stub.calls == 0


class TestEventsApi:
    def _store(self, client, short_name: str, headline: str, impact: str = "high"):
        return db.events.insert_event(
            short_name, headline=headline, why_it_matters="because",
            impact=impact, news_ids=[],
        )

    def test_defaults_to_the_watchlist(self, client):
        self._store(client, "AAPL", "Apple recalls chargers")
        self._store(client, "MSFT", "Microsoft buys a datacentre")   # not watched

        results = client.get("/events").json()["results"]
        assert [e["short_name"] for e in results] == ["AAPL"]

    def test_filters_by_symbol(self, client):
        self._store(client, "AAPL", "Apple recalls chargers")
        self._store(client, "6RJ0", "Rocket Lab wins a contract")

        results = client.get("/events", params={"symbols": "6RJ0"}).json()["results"]
        assert [e["headline"] for e in results] == ["Rocket Lab wins a contract"]

    def test_filters_by_days(self, client):
        self._store(client, "AAPL", "Apple recalls chargers")           # today
        old = self._store(client, "AAPL", "Apple opened a Bengaluru site")
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE events SET created_at = %s WHERE id = %s",
                (days_ago_iso(30), old),
            )

        week = client.get("/events", params={"days": 7}).json()["results"]
        assert [e["headline"] for e in week] == ["Apple recalls chargers"]

        quarter = client.get("/events", params={"days": 90}).json()["results"]
        assert len(quarter) == 2

    def test_orders_newest_first_and_breaks_ties_on_id(self, client):
        """Same created_at across rows: without the id tiebreaker Postgres may
        return them in a different order between two identical queries."""
        for n in range(6):
            self._store(client, "AAPL", f"Event {n}")
        with db.get_connection() as conn:
            conn.execute("UPDATE events SET created_at = '2026-08-01T00:00:00Z'")

        first = [e["id"] for e in client.get("/events").json()["results"]]
        second = [e["id"] for e in client.get("/events").json()["results"]]
        assert first == second
        # UUIDv7 sorts chronologically, so DESC puts the last-written first.
        assert first == sorted(first, reverse=True)

    def test_empty_is_a_real_answer(self, client):
        assert client.get("/events").json()["results"] == []

    def test_returned_shape(self, client):
        news_id = _articles(count=1)[0]
        db.events.insert_event(
            "AAPL", headline="Apple recalls chargers",
            why_it_matters="First recall since 2023.",
            previously_known="Reports of overheating circulated last week.",
            impact="high", news_ids=[news_id], tokens_total=150,
        )
        event = client.get("/events").json()["results"][0]
        assert event["headline"] == "Apple recalls chargers"
        assert event["previously_known"].startswith("Reports of overheating")
        assert event["impact"] == "high"
        assert event["news_ids"] == [str(news_id)]


class TestImpactOnNews:
    def test_news_exposes_and_filters_by_impact(self, client):
        ids = _articles(count=3)
        db.news.update_news(ids[0], impact="high")
        db.news.update_news(ids[1], impact="low")
        # ids[2] left unjudged

        everything = client.get("/news", params={"symbols": "AAPL"}).json()["results"]
        assert sorted(a["impact"] or "none" for a in everything) == ["high", "low", "none"]

        high = client.get("/news", params={"symbols": "AAPL", "impact": "high"}).json()
        assert [a["id"] for a in high["results"]] == [str(ids[0])]

    def test_unknown_impact_is_rejected(self, client):
        assert client.get("/news", params={"impact": "enormous"}).status_code == 422

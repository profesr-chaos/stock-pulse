"""Sentiment scoring.

The bar is directional correctness on real financial headlines, plus explicit
guards on the cases where general-purpose VADER is confidently wrong.
"""
from __future__ import annotations

import pytest
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from services import sentiment_service as sentiment

POSITIVE = [
    "Apple beats Q3 estimates as iPhone revenue tops forecasts",
    "Microsoft raises guidance after record cloud growth",
    "Rocket Lab wins $266 million Space Force launch contract",
    "Barclays raises price target on Nvidia to $250",
    "Nvidia upgraded to overweight on AI demand",
    "Shell announces $3.5bn buyback and raises dividend",
    "Tesla stock hits all-time high after delivery beat",
    "IVU Traffic Technologies AG raises earnings guidance for the full year",
]

NEGATIVE = [
    "Tesla misses delivery estimates, shares slide 8%",
    "Nvidia downgraded to underweight on AI spending concerns",
    "Boeing recalls 200000 units after safety probe launched",
    "Shell cuts dividend as profits collapse",
    "Firm issues profit warning, shares hit 52-week low",
    "Analyst cuts price target on Tesla citing weak demand",
    "Rocket Lab stock plunges after launch failure",
    "SEC investigation into accounting sends shares tumbling",
    "Company files for chapter 11 after default",
]

NEUTRAL = [
    "Apple to report Q3 earnings on Thursday",
    "Nvidia schedules investor day for September",
    "Shell publishes annual report",
]


class TestDirection:
    @pytest.mark.parametrize("headline", POSITIVE)
    def test_positive_headlines_score_positive(self, headline):
        assert sentiment.score(headline) > 0.15, headline

    @pytest.mark.parametrize("headline", NEGATIVE)
    def test_negative_headlines_score_negative(self, headline):
        assert sentiment.score(headline) < -0.15, headline

    @pytest.mark.parametrize("headline", NEUTRAL)
    def test_factual_announcements_stay_near_zero(self, headline):
        assert abs(sentiment.score(headline)) <= 0.2, headline

    def test_scores_stay_in_range(self):
        for headline in POSITIVE + NEGATIVE + NEUTRAL:
            assert -1.0 <= sentiment.score(headline) <= 1.0


class TestBeatsPlainVader:
    """Each of these is a case where stock VADER gets the sign wrong or has no
    opinion, which is why the lexicon override exists."""

    @pytest.mark.parametrize("headline", [
        "Tesla misses delivery estimates, shares slide 8%",
        "Boeing recalls 200000 units after safety probe launched",
        "Nvidia downgraded to underweight on AI spending concerns",
        "Firm issues profit warning, shares hit 52-week low",
    ])
    def test_negative_headlines_plain_vader_gets_wrong(self, headline):
        plain = SentimentIntensityAnalyzer().polarity_scores(headline)["compound"]
        tuned = sentiment.score(headline)
        assert tuned < -0.15
        assert plain >= tuned, f"expected the tuned score to be more negative: {headline}"


class TestPhraseCollapsing:
    def test_phrases_are_collapsed_to_single_tokens(self):
        assert "cuts_dividend" in sentiment._collapse_phrases("Shell cuts dividend today")

    def test_hyphenated_variants_are_matched(self):
        assert "52_week_low" in sentiment._collapse_phrases("shares hit 52-week low")

    def test_longest_phrase_wins(self):
        collapsed = sentiment._collapse_phrases("Analyst cuts price target on Tesla")
        assert "cuts_price_target" in collapsed

    def test_phrase_flips_the_sign_of_its_parts(self):
        """`dividend` alone is good news; `cuts dividend` is not. Whole-phrase
        scoring is the only way to get this right."""
        assert sentiment.score("Board approves dividend") > 0
        assert sentiment.score("Board cuts dividend") < 0

    def test_raises_guidance_and_raises_concerns_differ(self):
        assert sentiment.score("Firm raises guidance for the year") > 0
        assert sentiment.score("Report raises concerns over accounting") < 0


class TestDirectionWords:
    def test_down_is_negative(self):
        """Absent from stock VADER, yet "Is Down 7.6%" is the most common way a
        headline states the only fact that matters."""
        assert sentiment.score("Rocket Lab stock is down 7.6% today") < 0

    def test_up_is_positive(self):
        assert sentiment.score("Rocket Lab stock is up 7.6% today") > 0

    def test_higher_and_lower(self):
        assert sentiment.score("Shares open higher") > 0
        assert sentiment.score("Shares open lower") < 0


class TestBlending:
    def test_title_only_when_there_is_no_description(self):
        assert sentiment.score_article("Apple beats estimates") == \
            sentiment.score("Apple beats estimates")

    def test_the_title_outweighs_the_description(self):
        """Descriptions are frequently syndication boilerplate; scoring them
        equally flipped "Rocket Lab Is Down 7.6%" positive."""
        blended = sentiment.score_article(
            "Rocket Lab stock is down 7.6% after results",
            "Find out what this record-breaking milestone success means for you.",
        )
        title_only = sentiment.score("Rocket Lab stock is down 7.6% after results")
        assert blended < 0
        assert abs(blended - title_only) < abs(title_only)

    def test_empty_description_is_ignored(self):
        assert sentiment.score_article("Apple beats estimates", "   ") == \
            sentiment.score("Apple beats estimates")


class TestBackend:
    def test_default_backend_needs_no_model_download(self):
        assert sentiment.backend() == "vader"

    def test_finbert_request_falls_back_when_unavailable(self, monkeypatch):
        """A missing optional dependency must never fail a refresh."""
        import settings
        monkeypatch.setattr(settings, "SENTIMENT_BACKEND", "finbert")
        monkeypatch.setattr(sentiment, "_finbert", None)
        monkeypatch.setattr(sentiment, "_finbert_failed", False)
        monkeypatch.setattr(sentiment, "_get_finbert", lambda: None)
        assert sentiment.backend() == "vader"
        assert sentiment.score("Apple beats estimates") > 0

    def test_empty_input_is_safe(self):
        assert sentiment.score_many([]) == []
        assert sentiment.score("") == 0.0


class TestPersistence:
    def test_scores_are_written_to_the_rows(self, stocked_db):
        import db
        ids = db.news.insert_news_many([
            {"short_name": "AAPL", "title": "Apple beats Q3 estimates on iPhone strength",
             "title_key": "k1", "url": "https://a.com/1", "url_hash": "h1",
             "source": "Reuters", "source_domain": "reuters.com",
             "source_type": "GOOGLE_NEWS", "publish_time": "2026-07-29T10:00:00Z"},
            {"short_name": "AAPL", "title": "Apple misses estimates as revenue declines",
             "title_key": "k2", "url": "https://a.com/2", "url_hash": "h2",
             "source": "Reuters", "source_domain": "reuters.com",
             "source_type": "GOOGLE_NEWS", "publish_time": "2026-07-29T11:00:00Z"},
        ])
        assert sentiment.score_news_ids(ids) == 2
        scores = {r["title"].split(" Q3")[0].split(" estimates")[0]: r["sentiment"]
                  for r in db.news.get_news(["AAPL"])}
        assert scores["Apple beats"] > 0
        assert scores["Apple misses"] < 0

    def test_unscored_catch_up_pass(self, stocked_db):
        import db
        db.news.insert_news_many([
            {"short_name": "AAPL", "title": "Apple beats Q3 estimates on iPhone strength",
             "title_key": "k1", "url": "https://a.com/1", "url_hash": "h1",
             "source": "Reuters", "source_domain": "reuters.com",
             "source_type": "GOOGLE_NEWS", "publish_time": "2026-07-29T10:00:00Z"},
        ])
        assert sentiment.score_unscored() == 1
        assert db.news.get_unscored() == []

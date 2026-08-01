"""Story-level deduplication, relevance and clustering.

This is the module that decides feed quality, so the tests are written against
the failures that actually happened: cross-stock over-deduplication, Google's
OR-query bleed, Yahoo's generic-news fallback, and losing the best copy of a
story to a content farm's rewrite.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from normalize import now_utc
from services import dedup

from .conftest import article


class TestRelevance:
    def test_ticker_mention_counts(self):
        assert dedup.is_relevant("RKLB surges on new contract", "RKLB", "Rocket Lab Corp")

    def test_company_name_counts(self):
        assert dedup.is_relevant("Rocket Lab wins launch deal", "6RJ0", "Rocket Lab Corp")

    def test_resolved_symbol_alias_counts(self):
        """Trading212 calls it 6RJ0; every article says RKLB. Without the alias
        nothing would ever match."""
        assert dedup.is_relevant(
            "RKLB stock eyes worst month ever", "6RJ0", "Rocket Lab Corp",
            aliases=("RKLB",),
        )

    def test_unrelated_market_story_is_not_relevant(self):
        assert not dedup.is_relevant(
            "Warsh-led Fed leaves rates on hold", "IVU", "IVU Traffic Technologies"
        )

    @pytest.mark.parametrize("text", [
        "Apples are cheaper this autumn",          # 'apples' must not match AAPL
        "A new application framework launched",     # 'application' must not match APP
    ])
    def test_substring_matches_are_rejected(self, text):
        assert not dedup.is_relevant(text, "AAPL", "Apple")
        assert not dedup.is_relevant(text, "APP", "AppLovin")

    def test_legal_suffixes_are_ignored_when_matching(self):
        assert dedup.is_relevant("Eldorado Gold reports record output",
                                 "EGO", "Eldorado Gold Corp")


class TestFocusesOnOtherStock:
    def test_headline_leading_with_another_ticker_is_rejected(self):
        """The exact false positive Yahoo returned for a Rocket Lab query."""
        assert dedup.focuses_on_other_stock(
            "IBRX Stock Extends 5-Day Losing Streak", "6RJ0", ("RKLB",)
        )

    def test_headline_leading_with_our_ticker_is_kept(self):
        assert not dedup.focuses_on_other_stock(
            "RKLB Stock Eyes Worst Month Ever", "6RJ0", ("RKLB",)
        )

    def test_sector_headline_naming_no_ticker_is_kept(self):
        assert not dedup.focuses_on_other_stock(
            "Space stocks are falling hard", "6RJ0", ("RKLB",)
        )


class TestSpam:
    @pytest.mark.parametrize("title", [
        "Sponsored content: the best broker for you",
        "Advertisement - trade now with zero fees today",
    ])
    def test_advertising_is_dropped(self, title):
        assert dedup.is_spam({"title": title})

    def test_short_junk_headline_is_dropped(self):
        assert dedup.is_spam({"title": "Apple up"})

    def test_press_releases_are_kept(self):
        """A company's own earnings release is often the day's key item; the
        previous filter discarded every one of them."""
        assert not dedup.is_spam(
            {"title": "Apple Inc. announces Q3 results and declares dividend"}
        )


class TestChurn:
    """Unique, on-topic, zero-information filler. Nothing before this catches
    it, so if these leak the feed fills with them on a quiet day."""

    @pytest.mark.parametrize("title", [
        # Advice questions
        "Should You Buy Nvidia Stock Before August?",
        "Is It Too Late to Buy Apple Stock?",
        "Is Nvidia a Buy Right Now?",
        "Is Rocket Lab a Millionaire-Maker Stock?",
        "Where Will Nvidia Stock Be in 5 Years?",
        "Can Rocket Lab Make You a Fortune?",
        "Nvidia Stock: Buy, Sell, or Hold?",
        # Advice questions, as the live feed actually writes them: the question
        # trails the headline, and the subject is padded out to a full name.
        "NVIDIA (NASDAQ:NVDA) Stock Price Up 2.9% - Should You Buy?",
        "Is NVIDIA Corp. Stock a Buy Now?",
        "Is NVIDIA Corp (NVDA) a Bargain After 3.5% Drop?",
        "Is NVIDIA Corp (NVDA) The Best Jim Cramer Stock to Buy Now?",
        "Is NVIDIA Corp (NVDA) Stanley Druckenmiller's Best AI Stock Pick?",
        "Nvidia vs. AMD vs. Intel: Which Stock Is the Better Buy?",
        "NVIDIA vs. Sandisk: Which AI Stock Could Deliver Bigger Returns?",
        # Listicles
        "3 Reasons to Buy Apple Stock Like There's No Tomorrow",
        "5 Magnificent Stocks to Hold Forever",
        "Top 10 Growth Stocks for the Rest of 2026",
        "Best Growth Stocks to Buy for July 31st",
        "ASML and 21 More Stocks to Consider Buying Out of the AI Wreckage",
        "ASML, Lam Research, and a Ton of Other Stocks to Buy Right Now",
        # Fool-style hype
        "If You'd Invested $10,000 in Apple in 2015, Here's What You'd Have",
        "If You Invested $1,000 in Nvidia a Decade Ago",
        "This Stock Could Set You Up for Life",
        "Apple Stock Is a No-Brainer Buy Today",
        "Prediction: Nvidia Will Be Worth $10 Trillion",
        "Here's Why I Just Bought More Apple Stock",
        # Zacks / aggregator boilerplate
        "Apple (AAPL) Moves -0.55%: What You Should Know",
        "Nvidia (NVDA) Stock Sinks: What You Need to Know",
        "NVIDIA Corp Stock (NVDA) Closed Up by 3.46% on Jul 31: What Investors Need To Know",
        "NVIDIA (NASDAQ:NVDA) Shares Down 3.6% - Here's What Happened",
        "Why Apple (AAPL) Outpaced the Stock Market Today",
        "Wall Street Analysts Think Apple Could Rally",
        "Investors Heavily Search Apple Inc.: Here is What You Need to Know",
        "Is Apple a Great Stock According to Hedge Funds?",
    ])
    def test_churn_is_recognised(self, title):
        assert dedup.is_churn(title)

    @pytest.mark.parametrize("title", [
        # Analyst actions move prices and the sentiment lexicon scores them.
        "Morgan Stanley raises Rocket Lab price target to $75 from $60",
        "Apple downgraded to Neutral at Goldman Sachs",
        # Earnings and press releases.
        "Nvidia beats Q3 estimates as data centre revenue tops forecasts",
        "Apple Inc. announces Q3 results and declares dividend",
        # Real events, including event-reporting "why" headlines.
        "Apple recalls 200,000 chargers over overheating risk",
        "Why Nvidia fell 5% today after the CES keynote",
        "Rocket Lab wins $266M Space Force launch contract",
        # Live headlines the broader patterns must not swallow.
        "Naver shares surge as Nvidia invests $1B in AI data centre",
        "Michael Burry Sends Fresh Warning on Nvidia and Micron Stocks",
        "Micron, Sandisk and other chip stocks get major boosts after Microsoft's earnings",
        "Nvidia stock falls 5%: How credit risk sharing is impacting the AI trade",
    ])
    def test_real_news_survives(self, title):
        assert not dedup.is_churn(title)

    def test_churn_is_dropped_and_counted_by_prepare(self):
        batch = [
            article(title="Should You Buy Apple Stock Before August?",
                    url="https://fool.com/a"),
            article(title="3 Reasons to Buy Apple Stock Right Now",
                    url="https://fool.com/b"),
            article(title="Apple beats Q3 estimates as iPhone revenue tops forecasts",
                    url="https://reuters.com/c"),
        ]
        result = dedup.prepare(batch, "AAPL", "Apple")
        assert [r["url"] for r in result.rows] == ["https://reuters.com/c"]
        assert result.dropped["churn"] == 2


class TestPrepare:
    def test_same_story_from_many_outlets_stores_once(self):
        batch = [
            article(title="Apple unveils new AI chip for iPhones",
                    url="https://reuters.com/a", source_domain="reuters.com"),
            article(title="Apple unveils new AI chip for the iPhone",
                    url="https://fool.com/b", source_domain="fool.com"),
            article(title="Apple unveils a new AI chip for iPhones",
                    url="https://insidermonkey.com/c", source_domain="insidermonkey.com"),
        ]
        result = dedup.prepare(batch, "AAPL", "Apple")
        assert len(result.rows) == 1
        assert result.dropped["duplicate_story"] == 2

    def test_the_most_trustworthy_copy_wins_the_cluster(self):
        batch = [
            article(title="Apple unveils new AI chip for iPhones",
                    url="https://fool.com/b", source_domain="fool.com", image="https://i/x.jpg"),
            article(title="Apple unveils new AI chip for iPhones",
                    url="https://reuters.com/a", source_domain="reuters.com"),
        ]
        result = dedup.prepare(batch, "AAPL", "Apple")
        assert [r["source_domain"] for r in result.rows] == ["reuters.com"]

    def test_distinct_stories_are_both_kept(self):
        batch = [
            article(title="Apple unveils new AI chip for iPhones", url="https://reuters.com/a"),
            article(title="Tim Cook discusses Apple earnings outlook for 2027",
                    url="https://reuters.com/b"),
        ]
        assert len(dedup.prepare(batch, "AAPL", "Apple").rows) == 2

    def test_identical_url_shared_two_ways_stores_once(self):
        batch = [
            article(url="https://reuters.com/a?utm_source=x"),
            article(url="https://www.reuters.com/a/"),
        ]
        result = dedup.prepare(batch, "AAPL", "Apple")
        assert len(result.rows) == 1
        assert result.dropped["duplicate_url"] == 1

    def test_similar_headlines_far_apart_in_time_are_separate_stories(self):
        """A recurring headline shape is not the same story a week later."""
        old = now_utc() - timedelta(days=8)
        batch = [
            article(title="Apple shares climb as analysts raise price targets",
                    url="https://reuters.com/a"),
            article(title="Apple shares climb as analysts raise price targets",
                    url="https://reuters.com/b", published_at=old),
        ]
        assert len(dedup.prepare(batch, "AAPL", "Apple").rows) == 2

    def test_off_topic_google_result_is_dropped(self):
        batch = [article(title="Fed leaves rates on hold as inflation cools",
                         source_type="GOOGLE_NEWS")]
        result = dedup.prepare(batch, "AAPL", "Apple")
        assert result.rows == []
        assert result.dropped["off_topic"] == 1

    def test_yahoo_generic_fallback_is_dropped(self):
        """Yahoo's per-ticker feeds degrade to market news for thin tickers, so
        they must name the stock to count."""
        batch = [article(title="Jersey Mike's announces pricing of its IPO",
                         source_type="YAHOO_SEARCH")]
        result = dedup.prepare(batch, "IVU", "IVU Traffic Technologies")
        assert result.rows == []
        assert result.dropped["off_topic"] == 1

    def test_finviz_sector_story_is_kept_as_related(self):
        """Finviz's quote table is genuinely curated, so unnamed sector context
        there is real signal for the holder."""
        batch = [article(title="Space stocks are falling hard after FAA news",
                         source_type="FINVIZ", source_domain="marketwatch.com")]
        result = dedup.prepare(batch, "6RJ0", "Rocket Lab Corp", aliases=("RKLB",))
        assert len(result.rows) == 1
        assert result.rows[0]["relevance"] == dedup.RELATED

    def test_article_naming_the_stock_is_marked_direct(self):
        batch = [article(title="Rocket Lab wins $266M Space Force launch contract",
                         source_type="FINVIZ")]
        result = dedup.prepare(batch, "6RJ0", "Rocket Lab Corp", aliases=("RKLB",))
        assert result.rows[0]["relevance"] == dedup.DIRECT

    def test_direct_coverage_outranks_related_in_a_cluster(self):
        batch = [
            article(title="Space stocks slide after FAA deregulation news",
                    url="https://a.com/1", source_type="FINVIZ", source_domain="a.com"),
            article(title="Rocket Lab and space stocks slide after FAA deregulation news",
                    url="https://b.com/2", source_type="FINVIZ", source_domain="b.com"),
        ]
        result = dedup.prepare(batch, "6RJ0", "Rocket Lab Corp", aliases=("RKLB",))
        assert len(result.rows) == 1
        assert result.rows[0]["relevance"] == dedup.DIRECT

    def test_future_dated_article_is_rejected(self):
        batch = [article(published_at=now_utc() + timedelta(days=3))]
        assert dedup.prepare(batch, "AAPL", "Apple").rows == []

    def test_missing_title_or_url_is_dropped(self):
        batch = [article(title=""), article(url="")]
        result = dedup.prepare(batch, "AAPL", "Apple")
        assert result.rows == []
        assert result.dropped["malformed"] == 2

    def test_publish_time_is_stored_in_canonical_form(self):
        batch = [article(published_at="Wed, 29 Jul 2026 13:30:00 +0000")]
        rows = dedup.prepare(batch, "AAPL", "Apple").rows
        assert rows[0]["publish_time"] == "2026-07-29T13:30:00Z"


class TestPrepareAgainstStorage:
    def _stored(self, **overrides) -> dict:
        base = {
            "id": 7,
            "title": "Apple unveils new AI chip for iPhones",
            "title_key": "",
            "url_hash": "",
            "source_domain": "fool.com",
            "publish_time": now_utc().isoformat(),
            "has_image": 0,
            "has_description": 0,
        }
        base.update(overrides)
        return base

    def test_story_already_stored_is_not_inserted_again(self):
        result = dedup.prepare(
            [article(title="Apple unveils new AI chip for iPhones")],
            "AAPL", "Apple", existing=[self._stored()],
        )
        assert result.rows == []
        assert result.dropped["already_stored"] == 1

    def test_a_better_copy_enriches_the_stored_row_instead(self):
        """Nothing useful is thrown away: the duplicate contributes its image
        and description to the row we already hold."""
        result = dedup.prepare(
            [article(title="Apple unveils new AI chip for iPhones",
                     image="https://img/hero.jpg", description="Apple said today...")],
            "AAPL", "Apple", existing=[self._stored()],
        )
        assert result.enrichments == {
            7: {"image": "https://img/hero.jpg", "description": "Apple said today..."}
        }

    def test_stored_row_that_already_has_them_is_left_alone(self):
        result = dedup.prepare(
            [article(title="Apple unveils new AI chip for iPhones",
                     image="https://img/hero.jpg")],
            "AAPL", "Apple",
            existing=[self._stored(has_image=1, has_description=1)],
        )
        assert result.enrichments == {}

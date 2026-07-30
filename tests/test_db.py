"""Storage behaviour, migration, and the uniqueness rules that decide whether
articles survive.

The cross-stock test is the one that matters most: the previous build had a
global fuzzy duplicate check that made one stock's headline permanently block
every other stock's near-identical one, which is why the whole database held
332 articles.
"""
from __future__ import annotations

import sqlite3

import pytest

import db
import settings
from normalize import days_ago_iso, now_iso


def news_row(**overrides) -> dict:
    base = {
        "short_name": "AAPL",
        "title": "Stock Market Today: Nasdaq Rises As Powell Sees Improving Outlook",
        "title_key": "improving nasdaq outlook powell rises today",
        "url": "https://reuters.com/markets/1",
        "url_hash": "hash-1",
        "source": "Reuters",
        "source_domain": "reuters.com",
        "source_type": "GOOGLE_NEWS",
        "publish_time": "2026-07-29T13:30:00Z",
        "relevance": "direct",
    }
    base.update(overrides)
    return base


class TestSchema:
    def test_tables_are_created(self, temp_db):
        with db.get_connection() as conn:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"stocks", "news", "prices", "watchlist",
                "stock_sentiment_history", "stock_ai_summaries"} <= tables

    def test_auth_tables_are_gone(self, temp_db):
        with db.get_connection() as conn:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        assert not ({"users", "user_stocks", "user_industries"} & tables)

    def test_migration_is_idempotent(self, temp_db):
        db.create_tables()
        db.create_tables()
        assert db.stocks.count_stocks() == 0

    def test_wal_is_enabled(self, temp_db):
        with db.get_connection() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    def test_legacy_columns_and_rows_migrate(self, tmp_path, monkeypatch):
        """A pre-rewrite DB must upgrade in place, keeping its data."""
        path = tmp_path / "legacy.db"
        monkeypatch.setattr(settings, "DB_PATH", path)
        monkeypatch.setattr(db.connection, "_initialised", False)

        legacy = sqlite3.connect(path)
        legacy.executescript("""
            CREATE TABLE stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
                short_name TEXT NOT NULL, name TEXT NOT NULL, currency_code TEXT,
                type TEXT NOT NULL, industry TEXT, price REAL, price_change REAL,
                price_change_percent REAL, in_free_tier INTEGER DEFAULT 0,
                in_use INTEGER DEFAULT 0);
            CREATE TABLE news (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
                short_name TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT,
                source_country TEXT, source_type TEXT NOT NULL, lang TEXT,
                publish_time TEXT NOT NULL, url TEXT NOT NULL, image TEXT,
                title TEXT NOT NULL, description TEXT, sentiment REAL, AI_summary TEXT);
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);
            CREATE TABLE user_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
                user_id INTEGER, short_name TEXT, position INTEGER DEFAULT 0);
            INSERT INTO stocks (short_name, name, type, currency_code)
                VALUES ('AAPL','Apple','STOCK','USD');
            INSERT INTO news (short_name, source, source_type, publish_time, url, title)
                VALUES ('AAPL','investors.com','RSS',
                        'Wed, 28 Jan 2026 22:07:57 +0000',
                        'https://investors.com/a','Dow Jones Futures Rise As Meta Jumps');
            INSERT INTO user_stocks (user_id, short_name, position) VALUES (1,'AAPL',0);
            INSERT INTO user_stocks (user_id, short_name, position) VALUES (2,'AAPL',3);
        """)
        legacy.commit()
        legacy.close()

        db.create_tables()

        assert db.stocks.count_stocks() == 1
        # The watchlist is de-duplicated across the old per-user rows.
        assert db.watchlist.get_symbols() == ["AAPL"]
        # RFC-822 dates are rewritten to the canonical form.
        assert db.news.get_news(["AAPL"])[0]["publish_time"] == "2026-01-28T22:07:57Z"
        # Derived keys are populated for rows that predate them.
        assert db.news.get_news(["AAPL"])[0]["url_hash"]
        with db.get_connection() as conn:
            tables = {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "users" not in tables and "user_stocks" not in tables


class TestNewsUniqueness:
    def test_the_same_headline_is_stored_for_two_different_stocks(self, temp_db):
        """The regression that emptied the feed. A market-wide headline is
        relevant to every stock it mentions, and deduplication must never reach
        across stocks."""
        inserted = db.news.insert_news_many([
            news_row(short_name="NVDA", url_hash="shared"),
            news_row(short_name="TSLA", url_hash="shared"),
            news_row(short_name="AAPL", url_hash="shared"),
        ])
        assert len(inserted) == 3

    def test_the_same_article_is_not_stored_twice_for_one_stock(self, temp_db):
        db.news.insert_news_many([news_row()])
        assert db.news.insert_news_many([news_row()]) == []

    def test_different_articles_for_one_stock_both_store(self, temp_db):
        inserted = db.news.insert_news_many([
            news_row(url_hash="a", url="https://x.com/1"),
            news_row(url_hash="b", url="https://x.com/2", title="A different story entirely"),
        ])
        assert len(inserted) == 2

    def test_inserted_ids_come_back(self, temp_db):
        ids = db.news.insert_news_many([news_row()])
        assert db.news.get_news_by_id(ids[0])["short_name"] == "AAPL"

    def test_empty_batch_is_safe(self, temp_db):
        assert db.news.insert_news_many([]) == []


class TestNewsQueries:
    @pytest.fixture
    def seeded(self, temp_db):
        db.news.insert_news_many([
            news_row(url_hash="a", publish_time="2026-07-29T10:00:00Z",
                     title="Apple beats estimates today", sentiment=0.8),
            news_row(url_hash="b", publish_time="2026-07-20T10:00:00Z",
                     title="Apple misses estimates badly", sentiment=-0.8),
            news_row(url_hash="c", publish_time="2026-07-25T10:00:00Z",
                     title="Apple holds an event", sentiment=0.0),
            news_row(url_hash="d", short_name="TSLA", publish_time="2026-07-28T10:00:00Z",
                     title="Tesla recalls vehicles", sentiment=-0.5),
            news_row(url_hash="e", publish_time="2026-07-27T10:00:00Z",
                     title="Chip sector context piece", relevance="related"),
        ])
        return temp_db

    def test_newest_first(self, seeded):
        times = [r["publish_time"] for r in db.news.get_news(["AAPL"])]
        assert times == sorted(times, reverse=True)

    def test_filter_by_stock(self, seeded):
        assert {r["short_name"] for r in db.news.get_news(["TSLA"])} == {"TSLA"}

    def test_filter_by_multiple_stocks(self, seeded):
        assert {r["short_name"] for r in db.news.get_news(["AAPL", "TSLA"])} == {"AAPL", "TSLA"}

    def test_since_filter_uses_string_comparison_correctly(self, seeded):
        results = db.news.get_news(["AAPL"], since="2026-07-26T00:00:00Z")
        assert len(results) == 2

    @pytest.mark.parametrize("mood,expected", [("positive", 1), ("negative", 1), ("neutral", 2)])
    def test_sentiment_filter(self, seeded, mood, expected):
        assert len(db.news.get_news(["AAPL"], sentiment=mood)) == expected

    def test_relevance_filter(self, seeded):
        assert len(db.news.get_news(["AAPL"], relevance="related")) == 1
        assert len(db.news.get_news(["AAPL"], relevance="direct")) == 3

    def test_limit_is_respected(self, seeded):
        assert len(db.news.get_news(["AAPL"], limit=2)) == 2

    def test_no_symbols_returns_nothing_rather_than_everything(self, seeded):
        assert db.news.get_news([]) == []

    def test_counts_and_average_sentiment_by_stock(self, seeded):
        counts = {c["short_name"]: c for c in db.news.count_by_stock(since="2026-07-01")}
        assert counts["AAPL"]["article_count"] == 4
        assert counts["TSLA"]["avg_sentiment"] == pytest.approx(-0.5)

    def test_source_breakdown(self, seeded):
        rows = db.news.source_breakdown(["AAPL"], since="2026-07-01")
        assert rows[0]["source"] == "reuters.com" and rows[0]["article_count"] == 4

    def test_fingerprints_expose_what_is_already_stored(self, temp_db):
        db.news.insert_news_many([news_row(publish_time=now_iso(), image="https://i/x.jpg")])
        fingerprint = db.news.get_recent_fingerprints("AAPL")[0]
        assert fingerprint["url_hash"] == "hash-1"
        assert fingerprint["has_image"] and not fingerprint["has_description"]

    def test_old_fingerprints_are_outside_the_window(self, temp_db):
        db.news.insert_news_many([news_row(publish_time=days_ago_iso(30))])
        assert db.news.get_recent_fingerprints("AAPL", days=7) == []

    def test_google_links_are_excluded_from_image_fetching(self, temp_db):
        """Resolving a Google redirect costs a request and rarely yields one."""
        db.news.insert_news_many([
            news_row(url_hash="g", source_domain="news.google.com",
                     url="https://news.google.com/rss/articles/X"),
            news_row(url_hash="r", source_domain="reuters.com", url="https://reuters.com/a"),
        ])
        targets = db.news.get_missing_images(["AAPL"])
        assert [t["url"] for t in targets] == ["https://reuters.com/a"]

    def test_retention_prune(self, temp_db):
        db.news.insert_news_many([
            news_row(url_hash="old", publish_time="2020-01-01T00:00:00Z"),
            news_row(url_hash="new", publish_time=now_iso()),
        ])
        assert db.news.delete_older_than("2024-01-01T00:00:00Z") == 1
        assert len(db.news.get_news(["AAPL"], since="2000-01-01T00:00:00Z")) == 1


class TestWatchlist:
    def test_add_list_remove(self, temp_db):
        assert db.watchlist.add("AAPL")
        assert db.watchlist.get_symbols() == ["AAPL"]
        assert db.watchlist.remove("AAPL")
        assert db.watchlist.get_symbols() == []

    def test_adding_twice_is_rejected(self, temp_db):
        db.watchlist.add("AAPL")
        assert not db.watchlist.add("AAPL")

    def test_removing_something_absent_is_false(self, temp_db):
        assert not db.watchlist.remove("NOPE")

    def test_order_is_preserved_then_reorderable(self, temp_db):
        for symbol in ("AAPL", "TSLA", "MSFT"):
            db.watchlist.add(symbol)
        assert db.watchlist.get_symbols() == ["AAPL", "TSLA", "MSFT"]
        db.watchlist.reorder(["MSFT", "AAPL", "TSLA"])
        assert db.watchlist.get_symbols() == ["MSFT", "AAPL", "TSLA"]

    def test_symbols_not_in_the_catalogue_still_appear(self, temp_db):
        """A LEFT JOIN, so an unknown symbol shows up rather than vanishing."""
        db.watchlist.add("WEIRD")
        assert [r["short_name"] for r in db.watchlist.get_watchlist()] == ["WEIRD"]

    def test_backfill_tracking(self, temp_db):
        db.watchlist.add("AAPL")
        assert db.watchlist.needing_backfill() == ["AAPL"]
        db.watchlist.mark_backfilled("AAPL")
        assert db.watchlist.needing_backfill() == []


class TestStocks:
    def test_upsert_refreshes_names_without_duplicating(self, temp_db):
        db.stocks.bulk_upsert_stocks([
            {"shortName": "AAPL", "name": "Apple", "type": "STOCK", "currencyCode": "USD"}])
        db.stocks.bulk_upsert_stocks([
            {"shortName": "AAPL", "name": "Apple Inc", "type": "STOCK", "currencyCode": "USD"}])
        assert db.stocks.count_stocks() == 1
        assert db.stocks.get_stock("AAPL")["name"] == "Apple Inc"

    def test_get_stocks_preserves_caller_order(self, temp_db):
        db.stocks.bulk_upsert_stocks([
            {"shortName": s, "name": s, "type": "STOCK", "currencyCode": "USD"}
            for s in ("AAPL", "TSLA", "MSFT")])
        got = [s["short_name"] for s in db.stocks.get_stocks(["MSFT", "AAPL", "TSLA"])]
        assert got == ["MSFT", "AAPL", "TSLA"]

    def test_unknown_symbols_are_skipped_not_faked(self, temp_db):
        db.stocks.bulk_upsert_stocks([
            {"shortName": "AAPL", "name": "Apple", "type": "STOCK", "currencyCode": "USD"}])
        assert [s["short_name"] for s in db.stocks.get_stocks(["AAPL", "NOPE"])] == ["AAPL"]

    def test_update_only_touches_whitelisted_columns(self, temp_db):
        """The whitelist keeps caller-supplied keys out of the SQL string."""
        db.stocks.bulk_upsert_stocks([
            {"shortName": "AAPL", "name": "Apple", "type": "STOCK", "currencyCode": "USD"}])
        assert not db.stocks.update_stock("AAPL", **{"short_name = 'X' --": "hack"})
        assert db.stocks.update_stock("AAPL", industry="Tech")
        assert db.stocks.get_stock("AAPL")["industry"] == "Tech"

    def test_resolution_is_cached_on_the_row(self, temp_db):
        db.stocks.bulk_upsert_stocks([
            {"shortName": "6RJ0", "name": "Rocket Lab", "type": "STOCK", "currencyCode": "EUR"}])
        db.stocks.set_resolution("6RJ0", "RKLB", "NMS", "USD")
        row = db.stocks.get_stock("6RJ0")
        assert (row["yahoo_symbol"], row["exchange"], row["quote_currency"]) == ("RKLB", "NMS", "USD")
        assert row["resolved_at"]

    def test_search_finds_nothing_for_an_empty_query(self, temp_db):
        assert db.stocks.search_stocks("") == []


class TestPrices:
    def test_upsert_is_idempotent(self, temp_db):
        points = [("2026-07-28T00:00:00Z", 340.08), ("2026-07-29T00:00:00Z", 338.19)]
        db.prices.upsert_points("AAPL", points)
        db.prices.upsert_points("AAPL", points)
        assert len(db.prices.get_history("AAPL", "2026-07-01")) == 2

    def test_reruns_correct_a_revised_close(self, temp_db):
        db.prices.upsert_points("AAPL", [("2026-07-29T00:00:00Z", 1.0)])
        db.prices.upsert_points("AAPL", [("2026-07-29T00:00:00Z", 2.0)])
        assert db.prices.latest("AAPL")["close"] == 2.0

    def test_daily_and_snapshot_rows_coexist(self, temp_db):
        db.prices.upsert_points("AAPL", [("2026-07-29T00:00:00Z", 338.19)], interval="1d")
        db.prices.upsert_points("AAPL", [("2026-07-29T15:00:00Z", 340.00)], interval="snap")
        assert len(db.prices.get_history("AAPL", "2026-07-01")) == 2
        assert len(db.prices.get_history("AAPL", "2026-07-01", interval="1d")) == 1

    def test_series_prefers_the_daily_bar_and_fills_gaps_with_snapshots(self, temp_db):
        """A snapshot only appears for a day the daily feed hasn't closed yet —
        otherwise the chart would show two points for the same session."""
        db.prices.upsert_points("AAPL", [("2026-07-28T00:00:00Z", 340.08)], interval="1d")
        db.prices.upsert_points("AAPL", [("2026-07-28T15:00:00Z", 339.00)], interval="snap")
        db.prices.upsert_points("AAPL", [("2026-07-29T15:00:00Z", 338.19)], interval="snap")
        series = db.prices.get_series("AAPL", "2026-07-01")
        assert [(p["ts"], p["close"]) for p in series] == [
            ("2026-07-28T00:00:00Z", 340.08),
            ("2026-07-29T15:00:00Z", 338.19),
        ]

    def test_series_is_chronological(self, temp_db):
        db.prices.upsert_points("AAPL", [
            ("2026-07-29T00:00:00Z", 3.0), ("2026-07-27T00:00:00Z", 1.0),
            ("2026-07-28T00:00:00Z", 2.0)])
        assert [p["close"] for p in db.prices.get_series("AAPL", "2026-07-01")] == [1.0, 2.0, 3.0]

    def test_null_closes_are_not_stored(self, temp_db):
        db.prices.upsert_points("AAPL", [("2026-07-29T00:00:00Z", None)])
        assert db.prices.get_history("AAPL", "2026-07-01") == []

    def test_close_on_or_before(self, temp_db):
        db.prices.upsert_points("AAPL", [
            ("2026-07-20T00:00:00Z", 1.0), ("2026-07-25T00:00:00Z", 2.0)])
        assert db.prices.close_on_or_before("AAPL", "2026-07-24T00:00:00Z")["close"] == 1.0


class TestSentimentRollups:
    def _seed(self):
        db.news.insert_news_many([
            news_row(url_hash="a", publish_time="2026-07-29T10:00:00Z", sentiment=0.8),
            news_row(url_hash="b", publish_time="2026-07-29T11:00:00Z", sentiment=-0.6),
            news_row(url_hash="c", publish_time="2026-07-29T12:00:00Z", sentiment=0.05),
            news_row(url_hash="d", publish_time="2026-07-28T12:00:00Z", sentiment=-0.9),
        ])

    def test_a_day_is_rolled_up_with_buckets(self, temp_db):
        self._seed()
        assert db.sentiment.aggregate_day("2026-07-29") == 1
        row = [r for r in db.sentiment.get_history("AAPL", days=100000)
               if r["date"] == "2026-07-29"][0]
        assert row["article_count"] == 3
        assert row["positive_count"] == 1
        assert row["negative_count"] == 1
        assert row["neutral_count"] == 1
        assert row["avg_sentiment"] == pytest.approx((0.8 - 0.6 + 0.05) / 3)

    def test_grouping_works_because_dates_are_iso(self, temp_db):
        """The old table stored RFC-822 strings, so date() returned NULL and
        almost nothing ever aggregated."""
        self._seed()
        db.sentiment.aggregate_all(days=100000)
        dates = {r["date"] for r in db.sentiment.get_history("AAPL", days=100000)}
        assert {"2026-07-28", "2026-07-29"} <= dates

    def test_rollups_are_idempotent(self, temp_db):
        self._seed()
        db.sentiment.aggregate_day("2026-07-29")
        db.sentiment.aggregate_day("2026-07-29")
        rows = [r for r in db.sentiment.get_history("AAPL", days=100000)
                if r["date"] == "2026-07-29"]
        assert len(rows) == 1

    def test_unscored_articles_are_excluded(self, temp_db):
        db.news.insert_news_many([
            news_row(url_hash="x", publish_time="2026-07-29T10:00:00Z", sentiment=None)])
        assert db.sentiment.aggregate_day("2026-07-29") == 0


class TestSummaries:
    def test_latest_summary_wins(self, temp_db):
        db.summaries.insert_summary("AAPL", "older", tokens_total=10)
        db.summaries.insert_summary("AAPL", "newer", tokens_total=20)
        assert db.summaries.latest_summary("AAPL")["ai_summary"] == "newer"

    def test_no_summary_yet(self, temp_db):
        assert db.summaries.latest_summary("AAPL") is None


class TestConsentUrlRepair:
    """The previous scraper followed each Google redirect to "resolve" it and
    landed on Google's cookie-consent interstitial, saving that as the article
    URL. Those links open a cookie prompt instead of the story."""

    def _insert_raw(self, url: str, url_hash_value: str) -> None:
        with db.get_connection() as conn:
            conn.execute("""
                INSERT INTO news (short_name, source, source_type, publish_time,
                                  url, url_hash, title, title_key)
                VALUES ('AAPL', 'Reuters', 'SCRAPE', '2026-07-29T10:00:00Z', ?, ?,
                        'Apple beats Q3 estimates on iPhone demand', 'k1')
            """, (url, url_hash_value))

    def test_consent_wrapper_is_unwrapped_to_the_real_url(self, temp_db):
        self._insert_raw(
            "https://consent.google.com/ml?continue=https://news.google.com/rss/articles/CBMiABC",
            "old-hash",
        )
        db.create_tables()
        article = db.news.get_news(["AAPL"], since="2020-01-01T00:00:00Z")[0]
        assert article["url"] == "https://news.google.com/rss/articles/CBMiABC"
        assert article["source_domain"] == "news.google.com"

    def test_url_hash_is_recomputed_so_dedup_still_works(self, temp_db):
        self._insert_raw(
            "https://consent.google.com/ml?continue=https://reuters.com/tech/apple",
            "old-hash",
        )
        db.create_tables()
        article = db.news.get_news(["AAPL"], since="2020-01-01T00:00:00Z")[0]
        from normalize import url_hash
        assert article["url_hash"] == url_hash("https://reuters.com/tech/apple")

    def test_percent_encoded_targets_are_decoded(self, temp_db):
        self._insert_raw(
            "https://consent.google.com/ml?continue=https%3A%2F%2Freuters.com%2Ftech%2Fapple",
            "old-hash",
        )
        db.create_tables()
        assert db.news.get_news(["AAPL"], since="2020-01-01T00:00:00Z")[0]["url"] == \
            "https://reuters.com/tech/apple"

    def test_a_wrapper_with_no_target_is_dropped_not_kept_broken(self, temp_db):
        self._insert_raw("https://consent.google.com/ml?hl=en", "old-hash")
        db.create_tables()
        assert db.news.get_news(["AAPL"], since="2020-01-01T00:00:00Z") == []

    def test_repair_is_idempotent(self, temp_db):
        self._insert_raw(
            "https://consent.google.com/ml?continue=https://reuters.com/tech/apple",
            "old-hash",
        )
        db.create_tables()
        db.create_tables()
        assert len(db.news.get_news(["AAPL"], since="2020-01-01T00:00:00Z")) == 1

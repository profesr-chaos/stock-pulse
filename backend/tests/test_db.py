"""Storage behaviour, the SQLite import, and the uniqueness rules that decide
whether articles survive.

The cross-stock test is the one that matters most: the previous build had a
global fuzzy duplicate check that made one stock's headline permanently block
every other stock's near-identical one, which is why the whole database held
332 articles.
"""
from __future__ import annotations

import sqlite3
from uuid import UUID

import pytest

import db
import import_sqlite
from normalize import days_ago_iso, now_iso

_TABLES = "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public'"


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
            tables = {r["name"] for r in conn.execute(_TABLES)}
        assert {"stocks", "news", "prices", "watchlist",
                "stock_sentiment_history", "stock_ai_summaries"} <= tables

    def test_auth_tables_are_gone(self, temp_db):
        with db.get_connection() as conn:
            tables = {r["name"] for r in conn.execute(_TABLES)}
        assert not ({"users", "user_stocks", "user_industries"} & tables)

    def test_migration_is_idempotent(self, temp_db):
        db.create_tables()
        db.create_tables()
        assert db.stocks.count_stocks() == 0

    def test_ids_are_uuid_v7_and_sort_in_insertion_order(self, temp_db):
        """v7, not v4 — the timestamp lives in the leading bytes, so ids sort
        chronologically and `ORDER BY id DESC` stays a meaningful tiebreaker.
        A v4 id would satisfy "is a UUID" and shuffle this ordering.
        """
        ids = [db.news.insert_news_many([news_row(url_hash=f"h{i}")])[0] for i in range(6)]
        assert all(i.version == 7 for i in ids), [i.version for i in ids]
        assert ids == sorted(ids), "v7 ids must be monotonic across inserts"

    def test_search_is_case_insensitive(self, temp_db):
        """SQLite's LIKE ignored ASCII case and Postgres' does not, so the
        port had to switch to ILIKE or every search would have gone quiet."""
        db.stocks.bulk_upsert_stocks([
            {"shortName": "TSLA", "name": "Tesla Inc", "type": "STOCK", "currencyCode": "USD"}])
        assert [s["short_name"] for s in db.stocks.search_stocks("tesla")] == ["TSLA"]
        assert [s["short_name"] for s in db.stocks.search_stocks("tsla")] == ["TSLA"]


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

    def test_a_batch_past_the_bind_parameter_ceiling_still_stores(self, temp_db):
        """Postgres caps a statement at 65535 bind parameters — 4095 rows at 16
        columns — so a long backfill of a well-covered ticker has to chunk."""
        batch = [news_row(url_hash=f"h{i}", url=f"https://x.com/{i}") for i in range(4500)]
        assert len(db.news.insert_news_many(batch)) == 4500


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

    def test_sources_on_an_equal_count_come_back_in_a_stable_order(self, temp_db):
        """No unique tiebreaker means Postgres is free to reorder ties between
        two identical queries — the list would shuffle on every poll."""
        db.news.insert_news_many([
            news_row(url_hash="a", source_domain="zzz.com"),
            news_row(url_hash="b", source_domain="aaa.com"),
        ])
        first = [r["source"] for r in db.news.source_breakdown(["AAPL"], since="2026-07-01")]
        assert first == ["aaa.com", "zzz.com"]
        assert first == [r["source"] for r in db.news.source_breakdown(["AAPL"], since="2026-07-01")]

    def test_image_targets_on_an_equal_timestamp_are_stable(self, temp_db):
        db.news.insert_news_many([
            news_row(url_hash=f"h{i}", url=f"https://reuters.com/{i}",
                     publish_time="2026-07-29T10:00:00Z")
            for i in range(5)
        ])
        picked = [r["id"] for r in db.news.get_missing_images(["AAPL"], limit=3)]
        assert picked == sorted(picked, reverse=True)
        assert picked == [r["id"] for r in db.news.get_missing_images(["AAPL"], limit=3)]

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


class TestSqliteImport:
    """The one-way move off SQLite. Only run once for real, so it has to be
    right the first time: a lost row here is a lost row forever."""

    @pytest.fixture
    def legacy_db(self, tmp_path):
        path = tmp_path / "stocky.db"
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
                short_name TEXT, name TEXT, currency_code TEXT, type TEXT,
                sector TEXT, industry TEXT, yahoo_symbol TEXT, exchange TEXT,
                quote_currency TEXT, resolved_at TEXT, price REAL,
                price_change REAL, price_change_percent REAL, price_updated_at TEXT);
            CREATE TABLE news (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
                short_name TEXT, source TEXT, source_url TEXT, source_domain TEXT,
                source_country TEXT, source_type TEXT, lang TEXT, publish_time TEXT,
                url TEXT, url_hash TEXT, image TEXT, title TEXT, title_key TEXT,
                description TEXT, sentiment REAL, ai_summary TEXT, relevance TEXT);
            CREATE TABLE prices (short_name TEXT, ts TEXT, close REAL, interval TEXT);
            CREATE TABLE watchlist (
                short_name TEXT, created_at TEXT, position INTEGER, backfilled_at TEXT);
            CREATE TABLE stock_sentiment_history (
                short_name TEXT, date TEXT, avg_sentiment REAL, article_count INTEGER,
                positive_count INTEGER, negative_count INTEGER, neutral_count INTEGER,
                created_at TEXT);
            CREATE TABLE stock_ai_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, short_name TEXT,
                ai_summary TEXT, tokens_total INTEGER, days INTEGER, article_count INTEGER);

            INSERT INTO stocks (id, created_at, short_name, name, type, currency_code, price)
                VALUES (7, '2026-01-01T00:00:00Z', 'AAPL', 'Apple', 'STOCK', 'USD', 338.19);
            INSERT INTO news (id, created_at, short_name, source, source_domain,
                              source_type, publish_time, url, url_hash, title,
                              title_key, sentiment, relevance)
                VALUES (42, '2026-01-01T00:00:00Z', 'AAPL', 'Reuters', 'reuters.com',
                        'RSS', '2026-07-29T10:00:00Z', 'https://reuters.com/a', 'h1',
                        'Apple beats estimates', 'apple beats estimates', 0.8, 'direct');
            INSERT INTO prices VALUES ('AAPL', '2026-07-29T00:00:00Z', 338.19, '1d');
            INSERT INTO watchlist VALUES ('AAPL', '2026-01-01T00:00:00Z', 0, NULL);
            INSERT INTO stock_sentiment_history
                VALUES ('AAPL', '2026-07-29', 0.8, 1, 1, 0, 0, '2026-01-01T00:00:00Z');
            INSERT INTO stock_ai_summaries (id, created_at, short_name, ai_summary,
                                            tokens_total, days, article_count)
                VALUES (3, '2026-01-01T00:00:00Z', 'AAPL', 'good quarter', 10, 7, 1);
        """)
        old.commit()
        old.close()
        return path

    def test_every_table_comes_across(self, temp_db, legacy_db):
        counts = import_sqlite.import_from(legacy_db)
        assert counts == {"stocks": 1, "news": 1, "prices": 1, "watchlist": 1,
                          "stock_sentiment_history": 1, "stock_ai_summaries": 1}
        assert db.stocks.get_stock("AAPL")["price"] == 338.19
        assert db.news.get_news(["AAPL"])[0]["title"] == "Apple beats estimates"
        assert db.prices.latest("AAPL")["close"] == 338.19
        assert db.watchlist.get_symbols() == ["AAPL"]
        assert db.sentiment.get_history("AAPL", days=100000)[0]["article_count"] == 1
        assert db.summaries.latest_summary("AAPL")["ai_summary"] == "good quarter"

    def test_rows_get_fresh_uuids_rather_than_the_old_integer_ids(self, temp_db, legacy_db):
        """The old ids were 32-bit integers; there is nothing to carry into a
        UUID column, so every row takes a fresh one from the default."""
        import_sqlite.import_from(legacy_db)
        new_id = db.news.get_news(["AAPL"])[0]["id"]
        assert isinstance(new_id, UUID) and new_id.version == 7
        assert db.news.get_news_by_id(new_id)["title"] == "Apple beats estimates"

    def test_a_second_import_refuses_rather_than_duplicating(self, temp_db, legacy_db):
        import_sqlite.import_from(legacy_db)
        with pytest.raises(SystemExit):
            import_sqlite.import_from(legacy_db)

    def test_columns_that_kept_legacy_capitals_still_come_across(self, tmp_path, temp_db):
        """The real database declared `news.AI_summary`, not `ai_summary`.

        SQLite resolves column names case-insensitively, so every query worked
        and nobody noticed. A case-sensitive column match here skips the column
        without a word and drops every stored summary.
        """
        path = tmp_path / "capitals.db"
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE stocks (id INTEGER PRIMARY KEY, short_name TEXT, name TEXT, type TEXT);
            CREATE TABLE news (id INTEGER PRIMARY KEY, short_name TEXT, source TEXT,
                               source_type TEXT, publish_time TEXT, url TEXT,
                               url_hash TEXT, title TEXT, AI_summary TEXT);
            CREATE TABLE prices (short_name TEXT, ts TEXT, close REAL, interval TEXT);
            CREATE TABLE watchlist (short_name TEXT, position INTEGER);
            CREATE TABLE stock_sentiment_history (short_name TEXT, date TEXT);
            CREATE TABLE stock_ai_summaries (id INTEGER PRIMARY KEY, short_name TEXT,
                                             ai_summary TEXT);
            INSERT INTO news (id, short_name, source, source_type, publish_time, url,
                              url_hash, title, AI_summary)
                VALUES (1, 'AAPL', 'Reuters', 'RSS', '2026-07-29T10:00:00Z',
                        'https://reuters.com/a', 'h1', 'Apple beats', 'a cached summary');
        """)
        old.commit()
        old.close()

        import_sqlite.import_from(path)
        assert db.news.get_news(["AAPL"])[0]["ai_summary"] == "a cached summary"

    def test_a_database_missing_a_newer_column_still_imports(self, tmp_path, temp_db):
        """A .db taken before `sector` existed must not blow up on it."""
        path = tmp_path / "older.db"
        old = sqlite3.connect(path)
        old.executescript("""
            CREATE TABLE stocks (id INTEGER PRIMARY KEY, short_name TEXT,
                                 name TEXT, type TEXT);
            CREATE TABLE news (id INTEGER PRIMARY KEY, short_name TEXT, source TEXT,
                               source_type TEXT, publish_time TEXT, url TEXT, title TEXT);
            CREATE TABLE prices (short_name TEXT, ts TEXT, close REAL, interval TEXT);
            CREATE TABLE watchlist (short_name TEXT, position INTEGER);
            CREATE TABLE stock_sentiment_history (short_name TEXT, date TEXT);
            CREATE TABLE stock_ai_summaries (id INTEGER PRIMARY KEY, short_name TEXT,
                                             ai_summary TEXT);
            INSERT INTO stocks VALUES (1, 'AAPL', 'Apple', 'STOCK');
        """)
        old.commit()
        old.close()

        import_sqlite.import_from(path)
        assert db.stocks.get_stock("AAPL")["sector"] is None

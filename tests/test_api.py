"""The HTTP surface, end to end over a temporary database.

Covers the contract the frontend depends on, plus the input validation that
matters here specifically: there is no authentication, and symbols are
interpolated into outbound scraper URLs.
"""
from __future__ import annotations

import pytest

import db
from normalize import now_iso


class TestHealth:
    def test_health_reports_state(self, client):
        body = client.get("/health").json()
        assert body["ok"] is True
        assert body["watchlist"] == ["AAPL", "6RJ0"]
        assert body["sentiment_backend"] == "vader"
        assert isinstance(body["scrapers"], list)

    def test_openapi_is_served(self, client):
        assert client.get("/openapi.json").status_code == 200


class TestNoAuth:
    def test_no_auth_routes_remain(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert not [p for p in paths if "auth" in p or "login" in p or "register" in p]

    def test_no_user_or_subscription_routes_remain(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert not [p for p in paths if "/user" in p or "subscription" in p or "token" in p]

    def test_watchlist_needs_no_credentials(self, client):
        assert client.get("/watchlist").status_code == 200


class TestSearch:
    def test_finds_by_symbol(self, client):
        results = client.get("/stocks/search?q=AAPL").json()["results"]
        assert results[0]["symbol"] == "AAPL"

    def test_finds_by_name(self, client):
        results = client.get("/stocks/search?q=rocket").json()["results"]
        assert "6RJ0" in [r["symbol"] for r in results]

    def test_quote_currency_is_reported_over_the_catalogue_currency(self, client):
        """Trading212 lists Rocket Lab's German line as EUR; the price we store
        is the resolved USD one, so the label must follow the price."""
        results = client.get("/stocks/search?q=rocket").json()["results"]
        rocket = next(r for r in results if r["symbol"] == "6RJ0")
        assert rocket["currencyCode"] == "USD"
        assert rocket["yahooSymbol"] == "RKLB"

    def test_empty_query_is_rejected(self, client):
        assert client.get("/stocks/search?q=").status_code == 422

    def test_no_match_returns_an_empty_list(self, client):
        assert client.get("/stocks/search?q=zzzznotathing").json()["results"] == []


class TestQuotes:
    def test_returns_stored_quotes(self, client):
        results = client.get("/stocks/quotes?symbols=AAPL").json()["results"]
        assert results[0]["price"] == 338.19
        assert results[0]["changePercent"] == -0.556

    def test_order_and_count_match_the_request(self, client):
        results = client.get("/stocks/quotes?symbols=6RJ0,AAPL").json()["results"]
        assert [r["symbol"] for r in results] == ["6RJ0", "AAPL"]

    def test_unknown_symbol_returns_a_placeholder_not_an_error(self, client):
        results = client.get("/stocks/quotes?symbols=NOSUCH").json()["results"]
        assert results[0] == {"symbol": "NOSUCH", "name": None, "type": None,
                              "industry": None, "currencyCode": None, "exchange": None,
                              "yahooSymbol": None, "price": None, "change": None,
                              "changePercent": None, "priceUpdatedAt": None}

    def test_duplicates_are_collapsed(self, client):
        results = client.get("/stocks/quotes?symbols=AAPL,AAPL").json()["results"]
        assert len(results) == 1

    @pytest.mark.parametrize("bad", [
        "AA;DROP TABLE news", "../../etc/passwd", "<script>alert(1)</script>",
        "A" * 25, "http://evil.example/x",
    ])
    def test_malformed_symbols_are_rejected(self, client, bad):
        """These would otherwise be interpolated into an outbound scraper URL."""
        assert client.get("/stocks/quotes", params={"symbols": bad}).status_code == 400

    def test_symbol_count_is_capped(self, client):
        many = ",".join(f"SYM{i}" for i in range(80))
        assert client.get("/stocks/quotes", params={"symbols": many}).status_code == 400

    def test_missing_parameter_is_rejected(self, client):
        assert client.get("/stocks/quotes").status_code == 422


class TestStockDetail:
    def test_detail(self, client):
        body = client.get("/stocks/AAPL").json()
        assert body["symbol"] == "AAPL" and body["exchange"] == "NMS"

    def test_unknown_stock_is_404(self, client):
        assert client.get("/stocks/NOSUCH").status_code == 404

    def test_invalid_symbol_is_400(self, client):
        assert client.get("/stocks/" + "A" * 30).status_code == 400

    def test_path_traversal_does_not_reach_the_handler(self, client):
        assert client.get("/stocks/..%2Fetc").status_code == 404

    def test_price_history_shape(self, client):
        db.prices.upsert_points("AAPL", [
            ("2026-07-28T00:00:00Z", 340.08), ("2026-07-29T00:00:00Z", 338.19)])
        body = client.get("/stocks/AAPL/prices?days=30").json()
        assert body["symbol"] == "AAPL"
        assert body["currency"] == "USD"
        assert [p["close"] for p in body["points"]] == [340.08, 338.19]

    def test_price_history_for_unknown_stock_is_404(self, client):
        assert client.get("/stocks/NOSUCH/prices").status_code == 404

    def test_days_is_bounded(self, client):
        assert client.get("/stocks/AAPL/prices?days=5000").status_code == 422


class TestNewsFeed:
    @pytest.fixture(autouse=True)
    def seed(self, client):
        db.news.insert_news_many([
            {"short_name": "AAPL", "title": "Apple beats Q3 estimates on iPhone demand",
             "title_key": "k1", "url": "https://reuters.com/1", "url_hash": "h1",
             "source": "Reuters", "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
             "publish_time": "2026-07-29T10:00:00Z", "sentiment": 0.8, "relevance": "direct"},
            {"short_name": "AAPL", "title": "Apple faces an antitrust probe in Europe",
             "title_key": "k2", "url": "https://ft.com/2", "url_hash": "h2",
             "source": "FT", "source_domain": "ft.com", "source_type": "FINVIZ",
             "publish_time": "2026-07-28T10:00:00Z", "sentiment": -0.7, "relevance": "direct"},
            {"short_name": "6RJ0", "title": "Space stocks slide after FAA news",
             "title_key": "k3", "url": "https://mw.com/3", "url_hash": "h3",
             "source": "MarketWatch", "source_domain": "marketwatch.com",
             "source_type": "FINVIZ", "publish_time": "2026-07-27T10:00:00Z",
             "sentiment": -0.3, "relevance": "related"},
        ])

    def test_defaults_to_the_whole_watchlist(self, client):
        results = client.get("/news?days=365").json()["results"]
        assert {r["short_name"] for r in results} == {"AAPL", "6RJ0"}

    def test_newest_first(self, client):
        times = [r["publish_time"] for r in client.get("/news?days=365").json()["results"]]
        assert times == sorted(times, reverse=True)

    def test_filter_by_symbol(self, client):
        results = client.get("/news?symbols=6RJ0&days=365").json()["results"]
        assert [r["short_name"] for r in results] == ["6RJ0"]

    def test_filter_by_sentiment(self, client):
        results = client.get("/news?days=365&sentiment=negative").json()["results"]
        assert len(results) == 2 and all(r["sentiment"] < -0.2 for r in results)

    def test_filter_by_relevance(self, client):
        results = client.get("/news?days=365&relevance=related").json()["results"]
        assert [r["short_name"] for r in results] == ["6RJ0"]

    def test_since_filter(self, client):
        results = client.get("/news?since=2026-07-28T12:00:00Z").json()["results"]
        assert len(results) == 1

    def test_bad_since_is_rejected(self, client):
        assert client.get("/news?since=yesterday-ish").status_code == 400

    def test_bad_sentiment_value_is_rejected(self, client):
        assert client.get("/news?sentiment=amazing").status_code == 422

    def test_limit_is_bounded(self, client):
        assert client.get("/news?limit=9999").status_code == 422

    def test_articles_carry_the_fields_the_ui_needs(self, client):
        article = client.get("/news?days=365").json()["results"][0]
        for field in ("id", "title", "url", "publish_time", "source", "source_domain",
                      "sentiment", "relevance", "image", "description"):
            assert field in article

    def test_latest_returns_direct_coverage_only(self, client):
        db.news.insert_news_many([{
            "short_name": "AAPL", "title": "Apple ships a new laptop range today",
            "title_key": "k9", "url": "https://reuters.com/9", "url_hash": "h9",
            "source": "Reuters", "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
            "publish_time": now_iso(),
            "relevance": "direct",
        }])
        results = client.get("/news/latest").json()["results"]
        assert all(r["relevance"] == "direct" for r in results)

    def test_single_article(self, client):
        first = client.get("/news?days=365").json()["results"][0]
        assert client.get(f"/news/{first['id']}").json()["title"] == first["title"]

    def test_unknown_article_is_404(self, client):
        assert client.get("/news/999999").status_code == 404

    def test_sources_breakdown(self, client):
        results = client.get("/news/sources?days=90").json()["results"]
        assert {r["source"] for r in results} >= {"reuters.com", "ft.com"}

    def test_empty_watchlist_yields_an_empty_feed_not_everything(self, client):
        """A regression guard: an empty symbol set must not fall through to a
        dump of every article in the database."""
        db.watchlist.remove("AAPL")
        db.watchlist.remove("6RJ0")
        assert client.get("/news?days=365").json()["results"] == []


class TestWatchlistRoutes:
    def test_list_is_in_order_with_quotes_attached(self, client):
        results = client.get("/watchlist").json()["results"]
        assert [r["symbol"] for r in results] == ["AAPL", "6RJ0"]
        assert results[0]["price"] == 338.19

    def test_add_and_remove(self, client):
        assert client.post("/watchlist", json={"symbol": "TSLA"}).status_code == 201
        assert "TSLA" in db.watchlist.get_symbols()
        assert client.delete("/watchlist/TSLA").status_code == 200
        assert "TSLA" not in db.watchlist.get_symbols()

    def test_adding_triggers_a_backfill(self, client, monkeypatch):
        """Following a stock must populate its history immediately rather than
        leaving the feed empty until the next hourly tick."""
        calls = []
        import routes.watchlist as watchlist_routes
        monkeypatch.setattr(watchlist_routes.jobs, "backfill_stock",
                            lambda symbol, *a, **kw: calls.append(symbol))
        client.post("/watchlist", json={"symbol": "TSLA"})
        assert calls == ["TSLA"]

    def test_adding_twice_is_409(self, client):
        assert client.post("/watchlist", json={"symbol": "AAPL"}).status_code == 409

    def test_adding_something_not_in_the_catalogue_is_404(self, client):
        assert client.post("/watchlist", json={"symbol": "NOSUCH"}).status_code == 404

    def test_adding_a_malformed_symbol_is_400(self, client):
        assert client.post("/watchlist", json={"symbol": "A;DROP"}).status_code == 400

    def test_add_requires_a_symbol(self, client):
        assert client.post("/watchlist", json={}).status_code == 422

    def test_removing_something_absent_is_404(self, client):
        assert client.delete("/watchlist/TSLA").status_code == 404

    def test_symbols_are_case_insensitive(self, client):
        assert client.post("/watchlist", json={"symbol": "tsla"}).status_code == 201
        assert "TSLA" in db.watchlist.get_symbols()

    def test_reorder(self, client):
        client.put("/watchlist/reorder", json={"symbols": ["6RJ0", "AAPL"]})
        assert [r["symbol"] for r in client.get("/watchlist").json()["results"]] == \
            ["6RJ0", "AAPL"]

    def test_removing_a_stock_keeps_its_news_so_re_adding_is_instant(self, client):
        db.news.insert_news_many([{
            "short_name": "AAPL", "title": "Apple beats Q3 estimates on iPhone demand",
            "title_key": "k1", "url": "https://reuters.com/1", "url_hash": "h1",
            "source": "Reuters", "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
            "publish_time": "2026-07-29T10:00:00Z"}])
        client.delete("/watchlist/AAPL")
        assert len(db.news.get_news(["AAPL"], since="2020-01-01T00:00:00Z")) == 1

    def test_refresh_one_is_accepted(self, client):
        assert client.post("/watchlist/AAPL/refresh").status_code == 202

    def test_refreshing_an_unfollowed_stock_is_404(self, client):
        assert client.post("/watchlist/TSLA/refresh").status_code == 404


class TestInsights:
    @pytest.fixture(autouse=True)
    def seed(self, client):
        db.news.insert_news_many([
            {"short_name": "AAPL", "title": f"Apple story number {i} about earnings",
             "title_key": f"a{i}", "url": f"https://reuters.com/a{i}", "url_hash": f"ha{i}",
             "source": "Reuters", "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
             "publish_time": "2026-07-29T10:00:00Z", "sentiment": 0.6}
            for i in range(5)
        ] + [
            {"short_name": "6RJ0", "title": "Rocket Lab story about a launch failure",
             "title_key": "b1", "url": "https://reuters.com/b1", "url_hash": "hb1",
             "source": "Reuters", "source_domain": "reuters.com", "source_type": "GOOGLE_NEWS",
             "publish_time": "2026-07-29T10:00:00Z", "sentiment": -0.7},
        ])
        db.sentiment.aggregate_all(days=100000)

    def test_trending_has_the_three_panels(self, client):
        body = client.get("/insights/trending?days=30").json()
        assert set(body) == {"mostDiscussed", "mostPositive", "negativeSpikes"}

    def test_most_discussed_is_ranked_by_volume(self, client):
        body = client.get("/insights/trending?days=30").json()
        assert body["mostDiscussed"][0]["symbol"] == "AAPL"
        assert body["mostDiscussed"][0]["articleCount"] == 5

    def test_most_positive_is_ranked_by_sentiment(self, client):
        body = client.get("/insights/trending?days=30").json()
        assert body["mostPositive"][0]["symbol"] == "AAPL"

    def test_movers_are_ranked_by_absolute_price_move(self, client):
        db.stocks.bulk_set_quotes([
            {"short_name": "6RJ0", "price": 58.6, "change": -5.0,
             "change_percent": -8.28, "currency": "USD"}])
        results = client.get("/insights/movers?days=30").json()["results"]
        assert results[0]["symbol"] == "6RJ0"

    def test_movers_include_coverage_and_sentiment(self, client):
        results = client.get("/insights/movers?days=30").json()["results"]
        apple = next(r for r in results if r["symbol"] == "AAPL")
        assert apple["articleCount"] == 5 and apple["sentiment"] is not None

    def test_sentiment_history(self, client):
        results = client.get("/insights/sentiment/AAPL?days=180").json()["results"]
        assert results and results[0]["short_name"] == "AAPL"

    def test_panels_are_empty_rather_than_fabricated_when_nothing_is_followed(self, client):
        db.watchlist.remove("AAPL")
        db.watchlist.remove("6RJ0")
        body = client.get("/insights/trending").json()
        assert body == {"mostDiscussed": [], "mostPositive": [], "negativeSpikes": []}
        assert client.get("/insights/movers").json()["results"] == []


class TestAiSummaries:
    def test_disabled_without_a_key(self, client, monkeypatch):
        from services import ai_service
        monkeypatch.setattr(ai_service, "available", lambda: False)
        assert client.post("/news/stock/AAPL/ai-summary").status_code == 503

    def test_article_summary_requires_the_article_to_exist(self, client, monkeypatch):
        from services import ai_service
        monkeypatch.setattr(ai_service, "available", lambda: True)
        assert client.post("/news/999999/ai-summary").status_code == 404


class TestCors:
    def test_configured_origin_is_allowed(self, client):
        response = client.get("/health", headers={"Origin": "http://localhost:8080"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:8080"

    def test_wildcard_is_never_returned(self, client):
        """An unauthenticated API answering `*` lets any page you visit read and
        modify your watchlist."""
        response = client.get("/health", headers={"Origin": "https://evil.example"})
        assert response.headers.get("access-control-allow-origin") != "*"

    def test_credentials_are_not_enabled(self, client):
        response = client.get("/health", headers={"Origin": "http://localhost:8080"})
        assert response.headers.get("access-control-allow-credentials") != "true"


class TestRefresh:
    def test_refresh_is_accepted_and_runs_in_the_background(self, client, monkeypatch):
        import routes.system as system_routes
        calls = []
        monkeypatch.setattr(system_routes.jobs, "refresh_all", lambda: calls.append(1))
        assert client.post("/refresh").status_code == 202
        assert calls == [1]

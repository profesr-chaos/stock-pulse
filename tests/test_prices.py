"""Price parsing, currency normalisation and the fallback chain.

The currency tests are the important ones: an LSE quote arrives in pence, and
storing 3323.5 where 33.235 belongs is a silent 100x error in every chart and
percentage on the page.
"""
from __future__ import annotations

import pytest

from services import prices, yahoo


def chart_payload(currency="USD", price=338.19, previous=340.08, closes=None, stamps=None):
    closes = closes if closes is not None else [330.0, 336.91, 340.08, 338.19]
    stamps = stamps if stamps is not None else [1785072600, 1785159000, 1785245400, 1785331800]
    return {
        "chart": {
            "result": [{
                "meta": {
                    "symbol": "TEST", "exchangeName": "NMS", "fullExchangeName": "NasdaqGS",
                    "instrumentType": "EQUITY", "currency": currency,
                    "regularMarketPrice": price, "previousClose": previous,
                    "chartPreviousClose": 320.0,
                },
                "timestamp": stamps,
                "indicators": {"quote": [{"close": closes}]},
            }],
            "error": None,
        }
    }


class TestCurrencyNormalisation:
    def test_pence_becomes_pounds(self):
        assert yahoo.normalise_currency("GBp") == ("GBP", 100.0)

    def test_pounds_are_left_alone(self):
        assert yahoo.normalise_currency("GBP") == ("GBP", 1.0)

    @pytest.mark.parametrize("code,expected", [
        ("ILA", ("ILS", 100.0)),      # agorot
        ("ZAC", ("ZAR", 100.0)),      # cents
        ("USD", ("USD", 1.0)),
        ("EUR", ("EUR", 1.0)),
    ])
    def test_minor_units(self, code, expected):
        assert yahoo.normalise_currency(code) == expected

    def test_unknown_code_passes_through_rather_than_guessing(self):
        assert yahoo.normalise_currency("XYZ") == ("XYZ", 1.0)

    def test_missing_currency_is_safe(self):
        assert yahoo.normalise_currency(None) == ("", 1.0)


class TestParseChart:
    def test_quote_and_series_are_both_extracted(self):
        parsed = yahoo.parse_chart(chart_payload())
        assert parsed["price"] == 338.19
        assert parsed["exchange"] == "NMS"
        assert parsed["currency"] == "USD"
        assert len(parsed["points"]) == 4

    def test_change_is_computed_from_previous_close(self):
        parsed = yahoo.parse_chart(chart_payload(price=338.19, previous=340.08))
        assert parsed["change"] == pytest.approx(-1.89, abs=1e-6)
        assert parsed["change_percent"] == pytest.approx(-0.556, abs=1e-3)

    def test_an_lse_quote_is_converted_to_pounds_throughout(self):
        """Price, previous close and every history point must share one unit."""
        parsed = yahoo.parse_chart(
            chart_payload(currency="GBp", price=3323.5, previous=3234.5,
                          closes=[3200.0, 3234.5, 3323.5], stamps=[1, 2, 3])
        )
        assert parsed["currency"] == "GBP"
        assert parsed["price"] == pytest.approx(33.235)
        assert parsed["previous_close"] == pytest.approx(32.345)
        assert parsed["points"][-1][1] == pytest.approx(33.235)
        # Percentage change must be unaffected by the unit conversion.
        assert parsed["change_percent"] == pytest.approx(2.752, abs=1e-2)

    def test_market_holidays_with_null_closes_are_skipped(self):
        parsed = yahoo.parse_chart(
            chart_payload(closes=[330.0, None, 340.08, None], stamps=[1, 2, 3, 4])
        )
        assert [p[1] for p in parsed["points"]] == [330.0, 340.08]

    def test_timestamps_become_canonical_iso(self):
        parsed = yahoo.parse_chart(chart_payload())
        assert parsed["points"][-1][0] == "2026-07-29T13:30:00Z"

    def test_previous_close_falls_back_to_the_prior_bar(self):
        payload = chart_payload()
        del payload["chart"]["result"][0]["meta"]["previousClose"]
        parsed = yahoo.parse_chart(payload)
        assert parsed["previous_close"] == pytest.approx(340.08)

    @pytest.mark.parametrize("payload", [
        {}, {"chart": {}}, {"chart": {"result": []}}, {"chart": {"result": None}},
    ])
    def test_malformed_payloads_return_none_instead_of_raising(self, payload):
        assert yahoo.parse_chart(payload) is None

    def test_payload_with_no_price_at_all_returns_none(self):
        payload = chart_payload()
        payload["chart"]["result"][0]["meta"] = {"currency": "USD"}
        payload["chart"]["result"][0]["timestamp"] = []
        payload["chart"]["result"][0]["indicators"] = {"quote": [{"close": []}]}
        assert yahoo.parse_chart(payload) is None


class TestCnbcNumbers:
    @pytest.mark.parametrize("raw,expected", [
        ("3,323.50", 3323.5),
        ("-0.56%", -0.56),
        ("338.19", 338.19),
        (338.19, 338.19),
        ("UNCH", None),
        (None, None),
        ("", None),
    ])
    def test_display_strings_are_parsed(self, raw, expected):
        assert prices._to_float(raw) == expected


class TestCnbcSymbolCandidates:
    def test_yahoo_symbol_is_tried_first(self):
        """CNBC accepts `SHEL.L` directly, so no translation is needed."""
        assert prices._cnbc_candidates("SHEL.L")[0] == "SHEL.L"

    def test_suffix_is_translated_as_a_second_attempt(self):
        assert prices._cnbc_candidates("SHEL.L") == ["SHEL.L", "SHEL-GB"]
        assert prices._cnbc_candidates("SAP.DE") == ["SAP.DE", "SAP-DE"]

    def test_us_symbol_needs_no_translation(self):
        assert prices._cnbc_candidates("AAPL") == ["AAPL"]

    def test_unmapped_suffix_yields_only_the_original(self):
        assert prices._cnbc_candidates("XYZ.QQ") == ["XYZ.QQ"]


# Real Nasdaq shape. The two blocks swap meaning with the session: once the
# bell goes, `primaryData` becomes the extended-hours print and `secondaryData`
# holds the regular close.
NASDAQ_AFTER_HOURS = {"data": {
    "symbol": "AAPL", "exchange": "NASDAQ-GS", "marketStatus": "After-Hours",
    "primaryData": {
        "lastSalePrice": "$314.39", "netChange": "-19.04",
        "percentageChange": "-5.71%", "isRealTime": True,
        "lastTradeTimestamp": "Jul 30, 2026 7:26 PM ET",
    },
    "secondaryData": {
        "lastSalePrice": "$333.43", "netChange": "-4.76",
        "percentageChange": "-1.41%", "isRealTime": False,
        "lastTradeTimestamp": "Closed at Jul 30, 2026 4:00 PM ET",
    },
}}

NASDAQ_OPEN = {"data": {
    "symbol": "AAPL", "exchange": "NASDAQ-GS", "marketStatus": "Open",
    "primaryData": {
        "lastSalePrice": "$333.43", "netChange": "-4.76",
        "percentageChange": "-1.41%", "isRealTime": True,
        "lastTradeTimestamp": "Jul 30, 2026 2:10 PM ET",
    },
    "secondaryData": None,
}}


class TestNasdaqSource:
    def test_regular_session_price_wins_after_the_bell(self, monkeypatch):
        """Taking the live block blindly would store a 314.39 after-hours print
        as the day's close and put a point on the chart that neither Yahoo nor
        CNBC agrees with."""
        monkeypatch.setattr(prices.scraper, "get_json", lambda *a, **kw: NASDAQ_AFTER_HOURS)
        quote = prices.from_nasdaq("AAPL")
        assert quote["price"] == 333.43
        assert quote["change"] == -4.76
        assert quote["change_percent"] == -1.41
        assert quote["source"] == "nasdaq"

    def test_live_price_is_used_while_the_market_is_open(self, monkeypatch):
        monkeypatch.setattr(prices.scraper, "get_json", lambda *a, **kw: NASDAQ_OPEN)
        assert prices.from_nasdaq("AAPL")["price"] == 333.43

    def test_previous_close_is_derived_from_the_change(self, monkeypatch):
        monkeypatch.setattr(prices.scraper, "get_json", lambda *a, **kw: NASDAQ_AFTER_HOURS)
        assert prices.from_nasdaq("AAPL")["previous_close"] == 338.19

    def test_foreign_listings_are_refused_without_a_request(self, monkeypatch):
        """`SHEL.L` is the London ordinary; Nasdaq would answer with the New
        York ADR, at a different price in a different currency."""
        calls = []
        monkeypatch.setattr(prices.scraper, "get_json",
                            lambda *a, **kw: calls.append(a) or None)
        assert prices.from_nasdaq("SHEL.L") is None
        assert prices.from_nasdaq("^GSPC") is None
        assert calls == []

    def test_malformed_payloads_return_none_rather_than_raising(self, monkeypatch):
        for payload in (None, {}, {"data": None}, {"data": {}},
                        {"data": {"primaryData": {"lastSalePrice": "UNCH"}}}):
            monkeypatch.setattr(prices.scraper, "get_json", lambda *a, _p=payload, **kw: _p)
            assert prices.from_nasdaq("AAPL") is None


class TestFallbackChain:
    def test_nasdaq_is_used_when_yahoo_returns_nothing(self, monkeypatch):
        monkeypatch.setattr(prices, "from_yahoo", lambda *a, **kw: None)
        monkeypatch.setattr(prices, "from_nasdaq", lambda *a, **kw: {"price": 3.0, "source": "nasdaq"})
        monkeypatch.setattr(prices, "from_cnbc", lambda *a, **kw: {"price": 1.0, "source": "cnbc"})
        assert prices.get_quote("AAPL")["source"] == "nasdaq"

    def test_cnbc_is_used_when_yahoo_and_nasdaq_return_nothing(self, monkeypatch):
        monkeypatch.setattr(prices, "from_yahoo", lambda *a, **kw: None)
        monkeypatch.setattr(prices, "from_nasdaq", lambda *a, **kw: None)
        monkeypatch.setattr(prices, "from_cnbc", lambda *a, **kw: {"price": 1.0, "source": "cnbc"})
        assert prices.get_quote("AAPL")["source"] == "cnbc"

    def test_yahoo_is_preferred_when_available(self, monkeypatch):
        monkeypatch.setattr(prices, "from_yahoo", lambda *a, **kw: {"price": 2.0, "source": "yahoo"})
        monkeypatch.setattr(prices, "from_nasdaq", lambda *a, **kw: {"price": 3.0, "source": "nasdaq"})
        monkeypatch.setattr(prices, "from_cnbc", lambda *a, **kw: {"price": 1.0, "source": "cnbc"})
        assert prices.get_quote("AAPL")["source"] == "yahoo"

    def test_every_source_failing_returns_none(self, monkeypatch):
        monkeypatch.setattr(prices, "from_yahoo", lambda *a, **kw: None)
        monkeypatch.setattr(prices, "from_nasdaq", lambda *a, **kw: None)
        monkeypatch.setattr(prices, "from_cnbc", lambda *a, **kw: None)
        assert prices.get_quote("AAPL") is None


class TestStoring:
    def test_daily_bars_snap_to_midnight_so_one_day_is_one_row(self, stocked_db):
        """Exchanges report session times; without normalising, the same trading
        day would land in different rows depending on the venue."""
        import db
        prices._store("AAPL", {
            "price": 338.19, "change": -1.89, "change_percent": -0.556, "currency": "USD",
            "points": [("2026-07-29T13:30:00Z", 338.19), ("2026-07-28T13:30:00Z", 340.08)],
        })
        bars = db.prices.get_history("AAPL", "2026-07-01", interval="1d")
        assert [b["ts"] for b in bars] == ["2026-07-28T00:00:00Z", "2026-07-29T00:00:00Z"]

    def test_quote_is_written_to_the_stock_row(self, stocked_db):
        import db
        prices._store("AAPL", {"price": 400.0, "change": 1.0, "change_percent": 0.25,
                               "currency": "USD", "points": []})
        row = db.stocks.get_stock("AAPL")
        assert row["price"] == 400.0 and row["price_updated_at"]

    def test_unchanged_price_does_not_add_another_snapshot(self, stocked_db):
        """Overnight and weekend refreshes would otherwise stamp out a flat line
        of duplicate points."""
        import db
        prices._store_snapshot("AAPL", 338.19)
        first = db.prices.get_history("AAPL", "2000-01-01", interval="snap")
        prices._store_snapshot("AAPL", 338.19)
        assert db.prices.get_history("AAPL", "2000-01-01", interval="snap") == first

    def test_a_moved_price_does_add_a_snapshot(self, stocked_db):
        import db
        prices._store_snapshot("AAPL", 338.19)
        prices._store_snapshot("AAPL", 339.00)
        assert len(db.prices.get_history("AAPL", "2000-01-01", interval="snap")) >= 1
        assert db.prices.latest("AAPL")["close"] == 339.00

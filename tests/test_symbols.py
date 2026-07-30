"""Exchange hierarchy and symbol resolution.

`score_candidates` is pure, so the whole normalisation policy — the thing that
decides which of a company's many listings a price comes from — is testable
without a network.
"""
from __future__ import annotations

from services import symbols


def quote(symbol: str, exchange: str, longname: str, quote_type: str = "EQUITY") -> dict:
    return {"symbol": symbol, "exchange": exchange, "longname": longname,
            "shortname": longname, "quoteType": quote_type}


class TestExchangeRank:
    def test_hierarchy_is_us_then_london_then_xetra_then_rest_of_europe(self):
        assert (symbols.exchange_rank("NMS")
                < symbols.exchange_rank("LSE")
                < symbols.exchange_rank("GER")
                < symbols.exchange_rank("AMS"))

    def test_german_regional_venues_rank_below_xetra(self):
        """Same company, a fraction of the volume."""
        assert symbols.exchange_rank("GER") < symbols.exchange_rank("FRA")
        assert symbols.exchange_rank("GER") < symbols.exchange_rank("STU")

    def test_all_us_primaries_are_top_tier(self):
        for code in ("NMS", "NYQ", "NGM", "NCM"):
            assert symbols.exchange_rank(code) == 0

    def test_unknown_exchange_ranks_last(self):
        assert symbols.exchange_rank("WAT") > symbols.exchange_rank("SAO")
        assert symbols.exchange_rank(None) > symbols.exchange_rank("TYO")

    def test_is_us_listing(self):
        assert symbols.is_us_listing("NMS") and symbols.is_us_listing("nyq")
        assert not symbols.is_us_listing("LSE")
        assert not symbols.is_us_listing(None)


class TestScoreCandidates:
    def test_us_listing_wins_over_london_and_xetra(self):
        ranked = symbols.score_candidates("SHEL", "Shell", [
            quote("SHEL.L", "LSE", "Shell plc"),
            quote("SHEL", "NYQ", "Shell plc"),
            quote("R6C0.DE", "GER", "Shell plc"),
        ])
        assert ranked[0]["symbol"] == "SHEL"

    def test_us_listing_found_by_name_beats_local_code(self):
        """Trading212 calls Rocket Lab `6RJ0`; the point of resolution is to end
        up on RKLB so the price is the primary market's."""
        ranked = symbols.score_candidates("6RJ0", "Rocket Lab Corp", [
            quote("6RJ0.DE", "GER", "Rocket Lab Corporation"),
            quote("RKLB", "NMS", "Rocket Lab Corporation"),
        ])
        assert ranked[0]["symbol"] == "RKLB"

    def test_lse_international_board_line_is_demoted_below_xetra(self):
        """LSE International Board tickers all start with a digit (0NCA.L).
        Yahoo labels them plain "LSE" but they barely trade — IVU's London line
        had 15 daily bars in a month where its XETRA line had 23."""
        ranked = symbols.score_candidates("IVU", "IVU Traffic Technologies", [
            quote("0NCA.L", "LSE", "IVU Traffic Technologies AG"),
            quote("IVU.DE", "GER", "IVU Traffic Technologies AG"),
        ])
        assert ranked[0]["symbol"] == "IVU.DE"

    def test_ordinary_lse_listing_is_not_demoted(self):
        ranked = symbols.score_candidates("VOD", "Vodafone Group", [
            quote("VOD.DE", "GER", "Vodafone Group plc"),
            quote("VOD.L", "LSE", "Vodafone Group plc"),
        ])
        assert ranked[0]["symbol"] == "VOD.L"

    def test_a_different_company_sharing_a_ticker_is_rejected(self):
        ranked = symbols.score_candidates("APP", "AppLovin", [
            quote("APP", "NMS", "AppLovin Corporation"),
            quote("APP.AX", "ASX", "Appen Limited"),
        ])
        assert [c["symbol"] for c in ranked] == ["APP"]

    def test_leveraged_wrapper_is_not_the_underlying(self):
        ranked = symbols.score_candidates("TSLA", "Tesla", [
            quote("TSLA", "NMS", "Tesla, Inc."),
            quote("TSL3.L", "LSE", "Leverage Shares 3x Tesla ETP", "ETF"),
        ])
        assert [c["symbol"] for c in ranked] == ["TSLA"]

    def test_a_leveraged_instrument_still_resolves_to_a_leveraged_listing(self):
        ranked = symbols.score_candidates("3LTS", "Leverage Shares 3x Tesla", [
            quote("TSLA", "NMS", "Tesla, Inc."),
            quote("3LTS.L", "LSE", "Leverage Shares 3x Tesla ETP", "ETF"),
        ])
        assert ranked and ranked[0]["symbol"] == "3LTS.L"

    def test_currencies_and_futures_are_never_candidates(self):
        ranked = symbols.score_candidates("AAPL", "Apple", [
            quote("AAPL=F", "CME", "Apple Futures", "FUTURE"),
            quote("AAPLUSD", "CCC", "Apple", "CRYPTOCURRENCY"),
            quote("AAPL", "NMS", "Apple Inc."),
        ])
        assert [c["symbol"] for c in ranked] == ["AAPL"]

    def test_etfs_are_allowed_because_index_funds_are_tracked_too(self):
        ranked = symbols.score_candidates("VUAA", "Vanguard S&P 500 (Acc)", [
            quote("VUAA.L", "LSE", "Vanguard S&P 500 UCITS ETF", "ETF"),
        ])
        assert ranked[0]["symbol"] == "VUAA.L"

    def test_no_plausible_candidate_yields_nothing(self):
        assert symbols.score_candidates("ZZZZ", "Nonexistent Holdings", [
            quote("MSFT", "NMS", "Microsoft Corporation"),
        ]) == []

    def test_empty_candidate_list_is_safe(self):
        assert symbols.score_candidates("AAPL", "Apple", []) == []

    def test_candidates_without_a_symbol_are_skipped(self):
        assert symbols.score_candidates("AAPL", "Apple", [{"exchange": "NMS"}]) == []


class TestNameScore:
    def test_legal_suffix_differences_still_match(self):
        assert symbols.name_score("Apple", quote("AAPL", "NMS", "Apple Inc.")) > 80

    def test_unrelated_names_score_low(self):
        assert symbols.name_score("Apple", quote("MSFT", "NMS", "Microsoft Corp")) < 40

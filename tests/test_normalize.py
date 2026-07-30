"""Text, date and URL normalisation."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from normalize import (
    canonical_url,
    domain_of,
    parse_datetime,
    source_rank,
    strip_outlet_suffix,
    title_key,
    title_tokens,
    to_iso,
    url_hash,
    valid_symbol,
)


class TestParseDatetime:
    @pytest.mark.parametrize("raw", [
        "2026-07-29T13:30:00Z",
        "2026-07-29T13:30:00+00:00",
        "2026-07-29 13:30:00",
        "Wed, 29 Jul 2026 13:30:00 +0000",
        "Wed, 29 Jul 2026 13:30:00 GMT",
        1785331800,
        1785331800000,          # milliseconds
    ])
    def test_formats_all_land_on_the_same_instant(self, raw):
        assert to_iso(parse_datetime(raw)) == "2026-07-29T13:30:00Z"

    def test_rfc822_with_offset_is_converted_to_utc(self):
        assert to_iso(parse_datetime("Wed, 29 Jul 2026 15:30:00 +0200")) == "2026-07-29T13:30:00Z"

    def test_naive_input_is_treated_as_utc(self):
        assert to_iso(parse_datetime(datetime(2026, 7, 29, 13, 30))) == "2026-07-29T13:30:00Z"

    @pytest.mark.parametrize("raw", [None, "", "not a date at all", "   "])
    def test_unparseable_returns_none(self, raw):
        assert parse_datetime(raw) is None

    def test_storage_format_sorts_chronologically_as_a_string(self):
        """The whole point of one canonical format: `ORDER BY publish_time` and
        `since` comparisons are plain string operations."""
        stamps = [
            to_iso(parse_datetime("Wed, 29 Jul 2026 13:30:00 +0000")),
            to_iso(parse_datetime("2026-07-28T23:00:00Z")),
            to_iso(parse_datetime("2026-08-01T01:00:00Z")),
        ]
        assert sorted(stamps) == [
            "2026-07-28T23:00:00Z", "2026-07-29T13:30:00Z", "2026-08-01T01:00:00Z",
        ]

    def test_rfc822_string_would_not_have_sorted(self):
        """Guards the bug this replaced: raw feed dates sort alphabetically."""
        raw = ["Wed, 28 Jan 2026 22:07:57 +0000", "Wed, 25 Feb 2026 22:06:51 +0000"]
        assert sorted(raw) != raw  # 'Feb' < 'Jan' alphabetically — meaningless
        iso = [to_iso(parse_datetime(r)) for r in raw]
        assert sorted(iso) == iso


class TestCanonicalUrl:
    def test_tracking_parameters_are_stripped(self):
        assert canonical_url(
            "https://www.reuters.com/tech/apple?utm_source=twitter&utm_medium=social&id=7"
        ) == "https://reuters.com/tech/apple?id=7"

    def test_fragment_trailing_slash_and_case_are_normalised(self):
        assert canonical_url("HTTPS://WWW.Reuters.com/Tech/Apple/#section") == \
            "https://reuters.com/Tech/Apple"

    def test_query_order_does_not_change_identity(self):
        assert canonical_url("https://x.com/a?b=1&a=2") == canonical_url("https://x.com/a?a=2&b=1")

    def test_same_article_shared_two_ways_hashes_identically(self):
        a = "https://www.marketwatch.com/story/space-stocks?utm_campaign=email&mod=home"
        b = "https://marketwatch.com/story/space-stocks/"
        assert url_hash(a) == url_hash(b)

    def test_different_articles_do_not_collide(self):
        assert url_hash("https://x.com/a") != url_hash("https://x.com/b")

    def test_domain_of_drops_www(self):
        assert domain_of("https://www.ft.com/content/1") == "ft.com"


class TestTitles:
    @pytest.mark.parametrize("raw,expected", [
        ("Rocket Lab Stock Is Jumping for 2 Reasons - Barron's",
         "Rocket Lab Stock Is Jumping for 2 Reasons"),
        ("Apple beats estimates | Reuters", "Apple beats estimates"),
    ])
    def test_outlet_suffix_is_removed(self, raw, expected):
        assert strip_outlet_suffix(raw) == expected

    def test_short_headline_is_not_stripped_to_nothing(self):
        assert strip_outlet_suffix("Apple - Reuters") == "Apple - Reuters"

    def test_word_order_does_not_change_the_key(self):
        """The key is an order-independent bucket. Reworded headlines are left
        to the fuzzy matcher; this only has to survive reordering."""
        a = title_key("Apple beats Q3 profit estimates on iPhone demand")
        b = title_key("On iPhone demand, Apple beats Q3 profit estimates")
        assert a and a == b

    def test_stopwords_do_not_affect_the_key(self):
        a = title_key("Apple beats the Q3 profit estimates on iPhone demand")
        b = title_key("Apple beats Q3 profit estimates on iPhone demand")
        assert a and a == b

    def test_numbers_are_preserved_so_different_figures_differ(self):
        assert title_key("Tesla recalls 200000 vehicles over software") != \
               title_key("Tesla recalls 50000 vehicles over software")

    def test_thin_headline_yields_no_key(self):
        """Too little substance to be a safe dedup signal."""
        assert title_key("Apple is up") == ""

    def test_tokens_drop_stopwords_but_keep_finance_verbs(self):
        tokens = title_tokens("The Apple stock is set to beat the estimates")
        assert "beat" in tokens and "apple" in tokens
        assert "the" not in tokens and "is" not in tokens


class TestSourceRank:
    def test_wire_services_outrank_content_farms(self):
        assert source_rank("reuters.com") < source_rank("fool.com")

    def test_unresolved_google_link_ranks_worst(self):
        assert source_rank("news.google.com") > source_rank("insidermonkey.com")

    def test_subdomains_inherit_their_parent_rank(self):
        assert source_rank("uk.reuters.com") == source_rank("reuters.com")

    def test_unknown_domain_gets_the_middling_default(self):
        assert source_rank("reuters.com") < source_rank("some-blog.example") \
            < source_rank("news.google.com")


class TestValidSymbol:
    @pytest.mark.parametrize("symbol", ["AAPL", "6RJ0", "SHEL.L", "BRK-B", "RDS.A", "^GSPC"])
    def test_real_tickers_accepted(self, symbol):
        assert valid_symbol(symbol)

    @pytest.mark.parametrize("symbol", [
        "", "  ", "AA;DROP TABLE", "../../etc/passwd", "A" * 21,
        "AA PL", "<script>", "a\nb", "http://x.com",
    ])
    def test_anything_not_ticker_shaped_is_rejected(self, symbol):
        """These reach outbound scraper URLs, so the gate matters."""
        assert not valid_symbol(symbol)

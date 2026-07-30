"""Source parsers, against captured payloads.

Fixtures are trimmed copies of what each source actually returned, so a parser
that breaks when a source changes shape fails here rather than silently
returning an empty feed in production.
"""
from __future__ import annotations

import pytest

from services.news import finviz, google_news, images, publishers, yahoo_news

GOOGLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>"Rocket Lab" - Google News</title>
<item>
  <title>Rocket Lab (RKLB) Stock May Be 16% Undervalued Following Space Force Contract - Yahoo Finance</title>
  <link>https://news.google.com/rss/articles/CBMilAFBVV95cUxOX2JCTHktUFdC?oc=5</link>
  <guid isPermaLink="false">CBMilAFBVV95cUxOX2JCTHktUFdC</guid>
  <pubDate>Fri, 24 Jul 2026 21:12:05 GMT</pubDate>
  <source url="https://finance.yahoo.com">Yahoo Finance</source>
</item>
<item>
  <title>Rocket Lab Stock Is Jumping for 2 Reasons - Barron's</title>
  <link>https://news.google.com/rss/articles/CBMiekFVX3lxTE1HYlItT1lhb3RO?oc=5</link>
  <pubDate>Mon, 27 Jul 2026 15:02:00 GMT</pubDate>
  <source url="https://www.barrons.com">Barron's</source>
</item>
<item>
  <title>No link here</title>
  <pubDate>Mon, 27 Jul 2026 15:02:00 GMT</pubDate>
</item>
</channel></rss>
"""

FINVIZ_HTML = """
<html><body>
<table id="news-table">
  <tr><td width="130" align="right">Jul-29-26 09:41AM</td>
      <td><a href="https://www.investors.com/news/cathie-wood-ark">ARK Buys Millions In Falling Space Names</a>
          <span>(Investor's Business Daily)</span></td></tr>
  <tr><td width="130" align="right">08:41AM</td>
      <td><a href="https://www.barrons.com/articles/spacex-stock">SpaceX Needs Easier Regulations</a>
          <span>(Barrons.com)</span></td></tr>
  <tr><td width="130" align="right">Jul-28-26 04:53PM</td>
      <td><a href="/news/373579/45-investing-insights">Schaeffer's insights</a>
          <span>(Schaeffer's Research)</span></td></tr>
  <tr><td width="130" align="right">04:43PM</td>
      <td><a href="https://www.marketwatch.com/story/space-stocks">Space stocks are falling hard</a>
          <span>(MarketWatch)</span></td></tr>
  <tr><td>malformed row</td></tr>
</table>
</body></html>
"""


class TestGoogleNewsQuery:
    def test_company_name_is_a_phrase_and_ticker_is_qualified(self):
        """A bare ticker would match most of the internet — `APP` and `F` are
        ordinary words — so tickers only appear inside qualified phrases."""
        query = google_news.build_query("RKLB", "Rocket Lab Corp")
        assert '"Rocket Lab Corp"' in query
        assert '"RKLB stock"' in query
        assert " RKLB " not in f" {query} "

    def test_ambiguous_ticker_is_never_left_bare(self):
        query = google_news.build_query("APP", "AppLovin")
        assert '"AppLovin"' in query
        assert '"APP stock"' in query

    def test_ticker_equal_to_the_name_is_not_duplicated(self):
        assert google_news.build_query("BTC", "BTC") == '"BTC"'

    def test_missing_company_name_still_yields_a_query(self):
        assert google_news.build_query("RKLB", "") == '"RKLB stock" OR "RKLB shares"'


class TestGoogleNewsParse:
    def test_entries_are_parsed_with_publisher_and_date(self):
        articles = google_news._parse(GOOGLE_RSS)
        assert len(articles) == 2
        assert articles[0]["source"] == "Yahoo Finance"
        assert articles[0]["published_at"].isoformat().startswith("2026-07-24T21:12:05")

    def test_appended_outlet_is_stripped_from_the_title(self):
        articles = google_news._parse(GOOGLE_RSS)
        assert articles[1]["title"] == "Rocket Lab Stock Is Jumping for 2 Reasons"

    def test_publisher_name_is_mapped_to_a_domain(self):
        """Google's links are opaque redirects, so without this every item would
        look like it came from news.google.com and lose every dedup tie-break."""
        articles = google_news._parse(GOOGLE_RSS)
        assert articles[1]["source_domain"] == "barrons.com"
        assert articles[0]["source_domain"] == "finance.yahoo.com"

    def test_the_redirect_link_is_kept_because_it_still_works(self):
        """Resolving it needs a POST per article; the token redirects correctly
        in a browser, so we keep it and spend no requests."""
        articles = google_news._parse(GOOGLE_RSS)
        assert articles[0]["url"].startswith("https://news.google.com/rss/articles/")

    def test_entry_without_a_link_is_skipped(self):
        assert all(a["url"] for a in google_news._parse(GOOGLE_RSS))

    def test_empty_feed_is_safe(self):
        assert google_news._parse("") == []
        assert google_news._parse("<rss></rss>") == []


class TestFinvizParse:
    def test_rows_are_parsed_with_real_publisher_urls(self):
        articles = finviz.parse(FINVIZ_HTML)
        assert len(articles) == 4
        assert articles[0]["source_domain"] == "investors.com"
        assert articles[3]["source_domain"] == "marketwatch.com"

    def test_publisher_name_comes_from_the_row(self):
        assert finviz.parse(FINVIZ_HTML)[0]["source"] == "Investor's Business Daily"

    def test_time_only_rows_inherit_the_previous_date(self):
        """Finviz prints the date on the first row of a day and the time alone
        after it; without carrying it forward those rows lose their date."""
        articles = finviz.parse(FINVIZ_HTML)
        assert articles[0]["published_at"].date().isoformat() == "2026-07-29"
        assert articles[1]["published_at"].date().isoformat() == "2026-07-29"
        assert articles[2]["published_at"].date().isoformat() == "2026-07-28"
        assert articles[3]["published_at"].date().isoformat() == "2026-07-28"

    def test_market_times_are_converted_to_utc(self):
        """09:41 Eastern in July is 13:41 UTC."""
        assert finviz.parse(FINVIZ_HTML)[0]["published_at"].hour == 13

    def test_relative_links_are_absolute(self):
        assert finviz.parse(FINVIZ_HTML)[2]["url"].startswith("https://finviz.com/news/")

    def test_finviz_hosted_item_is_attributed_to_its_publisher(self):
        assert finviz.parse(FINVIZ_HTML)[2]["source_domain"] == "schaeffersresearch.com"

    def test_malformed_rows_are_skipped(self):
        assert all(a["title"] and a["url"] for a in finviz.parse(FINVIZ_HTML))

    def test_page_without_the_table_returns_nothing(self):
        assert finviz.parse("<html><body>blocked</body></html>") == []


class TestYahooThumbnails:
    def test_the_widest_resolution_wins(self):
        best = yahoo_news._best_thumbnail({"resolutions": [
            {"url": "https://i/small.jpg", "width": 140},
            {"url": "https://i/large.jpg", "width": 1200},
        ]})
        assert best == "https://i/large.jpg"

    @pytest.mark.parametrize("thumbnail", [None, {}, {"resolutions": []}, "nonsense"])
    def test_missing_thumbnails_are_safe(self, thumbnail):
        assert yahoo_news._best_thumbnail(thumbnail) is None

    def test_html_in_a_summary_is_stripped(self):
        assert yahoo_news._clean_summary("<p>Apple <b>beat</b> estimates</p>") == \
            "Apple beat estimates"


class TestPublisherMapping:
    @pytest.mark.parametrize("name,domain", [
        ("Barron's", "barrons.com"),
        ("Reuters", "reuters.com"),
        ("The Motley Fool", "fool.com"),
        ("Investor's Business Daily", "investors.com"),
        ("reuters.com", "reuters.com"),
        ("www.ft.com", "ft.com"),
    ])
    def test_known_publishers_map(self, name, domain):
        assert publishers.domain_for(name) == domain

    def test_unknown_publisher_gets_no_domain_rather_than_a_guess(self):
        """A wrong domain would corrupt source ranking; empty just means
        'average source'."""
        assert publishers.domain_for("Some Local Paper") == ""

    @pytest.mark.parametrize("name", [None, ""])
    def test_missing_publisher_is_safe(self, name):
        assert publishers.domain_for(name) == ""


class TestImageExtraction:
    def test_og_image_is_preferred(self):
        html = """<html><head>
            <meta property="og:image" content="https://cdn/hero.jpg">
            <meta name="twitter:image" content="https://cdn/other.jpg">
            </head><body><img src="https://cdn/inline.jpg"></body></html>"""
        assert images.extract_image(html, "https://x.com/a") == "https://cdn/hero.jpg"

    def test_twitter_image_is_the_fallback(self):
        html = '<html><head><meta name="twitter:image" content="https://cdn/t.jpg"></head></html>'
        assert images.extract_image(html, "https://x.com/a") == "https://cdn/t.jpg"

    def test_relative_urls_are_resolved(self):
        html = '<html><head><meta property="og:image" content="/img/hero.jpg"></head></html>'
        assert images.extract_image(html, "https://x.com/story/1") == "https://x.com/img/hero.jpg"

    def test_svgs_and_tracking_pixels_are_skipped(self):
        html = """<html><body>
            <img src="https://cdn/logo.svg">
            <img src="https://cdn/pixel.gif" width="1" height="1">
            <img src="https://cdn/real.jpg" width="800">
            </body></html>"""
        assert images.extract_image(html, "https://x.com/a") == "https://cdn/real.jpg"

    def test_page_with_no_usable_image(self):
        assert images.extract_image("<html><body><p>text</p></body></html>", "https://x.com") is None

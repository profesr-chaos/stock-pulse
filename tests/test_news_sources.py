"""The sources added for breadth: Bing News, Nasdaq RSS and SEC EDGAR.

Same contract as test_news_parsers.py — fixtures are trimmed copies of what
each source actually returned, so a parser that breaks when a source changes
shape fails here instead of quietly returning an empty feed in production.
"""
from __future__ import annotations

from services.news import bing_news, nasdaq_news, publishers, sec_edgar

# Bing wraps every link in an apiclick redirect that carries the real URL in a
# query param, and attributes republished stories as "<publisher> on MSN".
BING_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0" xmlns:News="https://www.bing.com/news/search">
<channel><title>"Rocket Lab" stock - BingNews</title>
<item>
  <title>Why Rocket Lab stock is soaring today</title>
  <link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;tid=6a6b&amp;url=https%3a%2f%2fwww.fool.com%2finvesting%2f2026%2f07%2f30%2fwhy-rocket-lab-stock-is-soaring%2f&amp;c=123</link>
  <description>Rocket Lab has bounced back from yesterday's rout.</description>
  <pubDate>Thu, 30 Jul 2026 11:30:25 GMT</pubDate>
  <News:Source>The Motley Fool on MSN</News:Source>
  <News:Image>http://www.bing.com/th?id=ONUT.g9SH&amp;pid=News</News:Image>
</item>
<item>
  <title>Rocket Lab stock is in freefall</title>
  <link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2finvezz.com%2fnews%2f2026%2f07%2f30%2frocket-lab-freefall%2f</link>
  <pubDate>Thu, 30 Jul 2026 02:28:00 GMT</pubDate>
  <News:Source>Invezz</News:Source>
</item>
<item>
  <title>Item with no link at all</title>
  <pubDate>Thu, 30 Jul 2026 02:28:00 GMT</pubDate>
</item>
</channel></rss>"""

NASDAQ_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
<channel><title>AAPL Feed</title>
<item>
  <title>Apple Inc. Bottom Line Climbs In Q3</title>
  <link>https://www.nasdaq.com/articles/apple-inc-bottom-line-climbs-q3</link>
  <description>(RTTNews) - Apple Inc. (AAPL) revealed a profit for its third quarter.</description>
  <pubDate>Thu, 30 Jul 2026 21:35:52 +0000</pubDate>
</item>
<item>
  <title></title>
  <link>https://www.nasdaq.com/articles/empty-title</link>
  <pubDate>Thu, 30 Jul 2026 20:00:00 +0000</pubDate>
</item>
</channel></rss>"""

# Real EDGAR shape: entry titles are "8-K  - Current report" with no company
# anywhere, and routine insider forms (4, 144) outnumber everything else.
SEC_ATOM = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Apple Inc.  (0000320193)</title>
  <entry>
    <title>8-K  - Current report</title>
    <filing-type>8-K</filing-type>
    <form-name>Current report</form-name>
    <filing-date>2026-07-30</filing-date>
    <filing-href>https://www.sec.gov/Archives/edgar/data/320193/000032019326000081-index.htm</filing-href>
  </entry>
  <entry>
    <title>4  - Statement of changes in beneficial ownership</title>
    <filing-type>4</filing-type>
    <form-name>Statement of changes in beneficial ownership of securities</form-name>
    <filing-date>2026-07-28</filing-date>
    <filing-href>https://www.sec.gov/Archives/edgar/data/320193/000032019326000079-index.htm</filing-href>
  </entry>
  <entry>
    <title>144  - Notice of proposed sale</title>
    <filing-type>144</filing-type>
    <form-name>Notice of proposed sale of securities</form-name>
    <filing-date>2026-07-27</filing-date>
    <filing-href>https://www.sec.gov/Archives/edgar/data/320193/000032019326000078-index.htm</filing-href>
  </entry>
  <entry>
    <title>10-Q/A  - Quarterly report</title>
    <filing-type>10-Q/A</filing-type>
    <form-name>Quarterly report [Sections 13 or 15(d)]</form-name>
    <filing-date>2026-07-25</filing-date>
    <filing-href>https://www.sec.gov/Archives/edgar/data/320193/000032019326000077-index.htm</filing-href>
  </entry>
</feed>"""



class TestBing:
    def test_redirect_is_unwrapped_to_the_publisher_url(self):
        articles = bing_news.parse(BING_RSS)
        assert articles[0]["url"] == (
            "https://www.fool.com/investing/2026/07/30/why-rocket-lab-stock-is-soaring/"
        )
        assert articles[0]["source_domain"] == "fool.com"

    def test_unwrapping_is_what_earns_the_dedup_tie_break(self):
        """A wrapped bing.com link would rank 6, below every real publisher."""
        from normalize import source_rank
        articles = bing_news.parse(BING_RSS)
        assert source_rank(articles[0]["source_domain"]) < source_rank("bing.com")

    def test_image_and_description_are_kept(self):
        article = bing_news.parse(BING_RSS)[0]
        assert article["image"] == "http://www.bing.com/th?id=ONUT.g9SH&pid=News"
        assert article["description"] == "Rocket Lab has bounced back from yesterday's rout."

    def test_publish_time_is_parsed(self):
        article = bing_news.parse(BING_RSS)[0]
        assert article["published_at"].year == 2026
        assert article["published_at"].month == 7

    def test_items_without_a_link_are_skipped(self):
        assert len(bing_news.parse(BING_RSS)) == 2

    def test_unwrap_leaves_anything_unexpected_alone(self):
        """A working redirect beats a mangled link."""
        assert bing_news.unwrap("https://www.fool.com/x") == "https://www.fool.com/x"
        assert bing_news.unwrap("http://www.bing.com/news/apiclick.aspx?ref=x") == (
            "http://www.bing.com/news/apiclick.aspx?ref=x"
        )

    def test_republisher_suffix_resolves_to_the_original_publisher(self):
        assert publishers.domain_for("The Motley Fool on MSN") == "fool.com"
        assert publishers.domain_for("Barron's on MSN") == "barrons.com"

    def test_query_does_not_use_google_s_or_syntax(self):
        """Bing answers a multi-term OR with an empty feed where Google returns
        a full one, so the two searches cannot share a query builder."""
        from services.news import google_news
        query = bing_news.build_query("RKLB", "Rocket Lab Corp")
        assert query == '"Rocket Lab Corp" stock'
        assert " OR " not in query
        assert " OR " in google_news.build_query("RKLB", "Rocket Lab Corp")

    def test_query_falls_back_to_the_ticker_without_a_company_name(self):
        assert bing_news.build_query("RKLB", "") == '"RKLB" stock'
        assert bing_news.build_query("", "") == ""


class TestNasdaq:
    def test_parses_title_link_and_summary(self):
        article = nasdaq_news.parse(NASDAQ_RSS)[0]
        assert article["title"] == "Apple Inc. Bottom Line Climbs In Q3"
        assert article["url"] == "https://www.nasdaq.com/articles/apple-inc-bottom-line-climbs-q3"
        assert article["description"].startswith("(RTTNews)")
        assert article["source_domain"] == "nasdaq.com"
        assert article["source_type"] == "NASDAQ"

    def test_untitled_items_are_skipped(self):
        assert len(nasdaq_news.parse(NASDAQ_RSS)) == 1

    def test_is_not_trusted_for_articles_that_never_name_the_stock(self):
        """Asking Nasdaq for an unknown symbol returns generic market news
        rather than an empty feed, exactly like Yahoo's symbol-keyed
        endpoints — so it must never be allowed to contribute `related`."""
        from services.dedup import _RELATED_ALLOWED
        assert nasdaq_news.SOURCE_TYPE not in _RELATED_ALLOWED


class TestSecEdgar:
    def test_routine_insider_filings_are_dropped(self):
        """Forms 4 and 144 arrive dozens a month and would swamp the feed."""
        forms = [a["description"] for a in sec_edgar.parse(SEC_ATOM, "Apple Inc.")]
        assert len(forms) == 2
        assert not any("beneficial ownership" in f for f in forms)

    def test_amendments_count_as_material(self):
        titles = [a["title"] for a in sec_edgar.parse(SEC_ATOM, "Apple Inc.")]
        assert "Apple Inc. filed 10-Q/A: Quarterly report [Sections 13 or 15(d)]" in titles

    def test_title_names_the_company_because_the_filed_one_does_not(self):
        """EDGAR titles are "8-K  - Current report": no company, no ticker. Left
        as filed, every item would fail the relevance check and every 8-K would
        collide on the same dedup key."""
        from services.dedup import is_relevant
        article = sec_edgar.parse(SEC_ATOM, "Apple Inc.")[0]
        assert article["title"] == "Apple Inc. filed 8-K: Current report"
        assert is_relevant(article["title"], "AAPL", "Apple Inc.")

    def test_filing_date_and_link_are_kept(self):
        article = sec_edgar.parse(SEC_ATOM, "Apple Inc.")[0]
        assert article["published_at"].date().isoformat() == "2026-07-30"
        assert article["url"].startswith("https://www.sec.gov/Archives/")
        assert article["source_domain"] == "sec.gov"

    def test_the_filing_outranks_everyone_reporting_on_it(self):
        from normalize import source_rank
        assert source_rank("sec.gov") < source_rank("fool.com")

    def test_unknown_ticker_returns_an_html_page_with_no_entries(self):
        assert sec_edgar.parse("<html><body>No matching companies.</body></html>", "X") == []

    def test_is_skipped_entirely_without_a_declared_contact(self, monkeypatch):
        """SEC enforces its fair-access policy with 403s. No contact configured
        means the request would be refused anyway, so don't make it."""
        import settings
        calls = []
        monkeypatch.setattr(settings, "SEC_CONTACT", None)
        monkeypatch.setattr(sec_edgar.scraper, "get", lambda *a, **kw: calls.append(a))
        assert sec_edgar.fetch("AAPL", "Apple Inc.") == []
        assert calls == []

    def test_material_form_prefixes(self):
        assert sec_edgar.is_material("8-K")
        assert sec_edgar.is_material("424B5")
        assert sec_edgar.is_material("DEF 14A")
        assert not sec_edgar.is_material("4")
        assert not sec_edgar.is_material("SC 13G/A")

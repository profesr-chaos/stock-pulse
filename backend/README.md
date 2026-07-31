# Stocky Backend

News and prices for the stocks you follow, scraped from free sources. No API
keys required, no accounts, no subscription tiers — a single-user local tool.

The two things it has to do well:

1. **News.** One article per *story*, not fifty copies of the same wire report,
   with the most trustworthy outlet's version kept.
2. **Prices.** One canonical listing per company so numbers are comparable, in
   the currency they are actually quoted in, refreshed every few minutes while
   a market is open, with a month of history behind them.

---

## How the data is obtained

Everything goes through `services/http_client.py`, one adaptive scraper shared
by all sources. Per host it keeps a token bucket whose rate ratchets *up* while
responses stay clean and halves the moment a host answers 429/403/503; it obeys
`Retry-After`, retries with exponential backoff and full jitter, opens a circuit
breaker after repeated failures, and presents a stable, internally consistent
browser fingerprint per host (rotated only when that host starts pushing back).
HTTP/2 and connection reuse are on, and a 5-minute response cache means several
scrapers wanting the same feed in one refresh cost one request.

Not included: proxy rotation or anything that defeats an access control rather
than sharing a host's capacity. Where a source pushes back, the answer is
another source.

### News sources (queried concurrently, merged, deduplicated)

Seven fetches across five independent operators — Google, Yahoo, Microsoft,
Finviz, Nasdaq and the SEC — so no single company's outage or rate limit takes
the feed down. Spreading the work this way is also what keeps it welcome: seven
polite fetches across five operators is far kinder to each than hammering one.

| Source | Why it's there | Caveat |
|---|---|---|
| Google News RSS | Broadest reach; the only one that can backfill a month, via `after:`/`before:` windows | Links are opaque redirects — see below |
| Yahoo search JSON | The only free source of article thumbnails that costs no extra request | Falls back to generic market news for thin tickers |
| Yahoo per-ticker RSS | Article summaries | Same fallback caveat |
| Bing News RSS | A second search index, independent of Google, with images and descriptions. Carries the thin non-US tickers Google returns nothing for | Needs its own query shape — see below |
| Finviz quote page | Real publisher URLs, dense coverage, genuinely curated per ticker | US listings only |
| Nasdaq per-ticker RSS | Wire copy (RTTNews, Zacks) and Nasdaq editorial, real URLs, on a host nothing else here touches | US only; returns *generic* market news for unknown symbols, so it is not trusted for `related` |
| SEC EDGAR Atom | The filing itself — the 8-K lands here before anyone reports on it. Cannot be paywalled or go stale | US only, opt-in: needs `STOCKY_SEC_CONTACT` |

**Bing's query.** Google's `"Company" OR "TICK stock" OR "TICK shares"` returns
a full feed there and an *empty* one on Bing, which answers a multi-term OR with
zero items. Bing gets a single quoted phrase plus the word `stock` instead, so
the two cannot share a query builder. Its links are `apiclick.aspx` redirects
that carry the real URL in a query parameter, so unwrapping costs no request and
Bing items arrive with the publisher's own domain — which means they *win* dedup
tie-breaks that a Google copy of the same story would lose.

**EDGAR is opt-in.** The SEC's fair-access policy requires a contact address in
the User-Agent and enforces it: a UA carrying a repo URL gets a flat 403, the
same request with an email returns 200. So the source switches on only when
`STOCKY_SEC_CONTACT` is set. Filed titles are useless as-is (`"8-K  - Current
report"` — no company, no ticker), so the title is constructed from the company
name and form, and routine insider paperwork (forms 3/4/5, 144) is filtered out.

**Rejected: GDELT.** Its worldwide index looks like the obvious way to cover
non-US listings, but the phrase search is too loose to use — `"shell"` returns
awards shows and retirement advice, and the legal suffix that would make it
precise (`"Shell plc"`) appears in almost no body copy. With a 20-second TLS
handshake and a 429 at one request per five seconds on top, it cost more latency
per refresh than every other source combined while contributing articles the
relevance filter then dropped. Bing supplies the non-US reach it was added for.

**Google's links.** Since Google changed its redirect format, the
`/rss/articles/CBMi…` payload is an opaque token, not a base64 URL, and
recovering the publisher's link needs a POST per article. The token still
redirects correctly in a browser, so the link is kept as-is and attribution
comes from the feed's `<source>` element, mapped to a domain in
`services/news/publishers.py`. Zero extra requests, correct publisher, working
link.

### Price sources (fallback chain)

1. **Yahoo chart v8** — quote *and* daily history in one request, across two
   hostnames (`query1`/`query2`) so a throttled one fails over to the other.
2. **Nasdaq quote API** — US listings, real-time during the session, own host,
   no key. Refuses suffixed symbols on purpose: `SHEL.L` is the London
   ordinary, and Nasdaq would answer with the New York ADR at a different price
   in a different currency.
3. **CNBC quote API** — independent host, no key, global coverage. Accepts
   Yahoo-style symbols (`SHEL.L`) directly.

Three operators, so a throttled Yahoo means the next source picks up the slack
rather than the refresh failing. Verified agreeing to the cent on AAPL, RKLB and
SHEL.L.

Nasdaq splits a quote into `primaryData` (whatever is trading right now) and
`secondaryData` (the regular close once the bell goes). The regular-session
figure wins whenever it is present — taking the live block blindly would store
an after-hours print as the day's close and put a point on the chart that
neither other source agrees with.

History comes from Yahoo only; if Yahoo is unavailable the quote still updates
from a fallback and the stored history stops extending. Degraded, not broken.

**Freshness.** The scheduler ticks every `STOCKY_PRICE_REFRESH_OPEN_MINUTES`
(5) and `jobs.refresh_prices` drops most of those ticks back to the hourly
interval once every market is shut — a closed market's price cannot move, so
polling it would be load on someone else's servers for an unchanged number. The
watchlist refresh itself runs concurrently, so a twenty-stock list is one round
trip deep rather than twenty.

---

## Exchange normalisation

The same company trades on many venues in many currencies, and the Trading212
catalogue is not a reliable guide to which one — it lists TSLA as an EUR
instrument. So listings are resolved against Yahoo search and ranked by
exchange (`services/symbols.py`):

```
US primary → London → XETRA → rest of western Europe → Canada
           → German regional → depositary receipts → everything else
```

The winner is confirmed to actually return a quote before being cached on the
stock row. Two rules earn their keep:

- Local codes get a second search **by company name**: Trading212 calls Rocket
  Lab `6RJ0`, and only a name search surfaces `RKLB` on NASDAQ.
- LSE International Board tickers (all of which start with a digit, e.g.
  `0NCA.L`) are demoted. Yahoo labels them plain "LSE" but they are
  cross-listings that barely trade — IVU's London line had 15 daily bars in a
  month where its XETRA line had 23.

Prices are always stored in **major** currency units: LSE quotes arrive in pence
and Tel Aviv in agorot, and a chart that silently mixes 3323.5 with 33.235 is
worse than no chart.

---

## Deduplication

`services/dedup.py`. Identity is a canonical URL hash (tracking parameters
stripped), enforced by a unique index on `(short_name, url_hash)`.
Near-duplicates are clustered **per stock, within ±72 hours** and each cluster
elects a winner by source quality, then by whether it has an image and a
description. If an incoming article duplicates one already stored it is not
inserted, but any image or description the stored row lacks is copied onto it.

Articles are tagged `direct` (names the stock) or `related` (sector context from
Finviz's curated table that never names it), so the feed can separate them
without discarding either.

For reference, on a fresh follow of Shell: **630 articles found → 418 stored**,
having dropped 120 duplicate stories, 29 duplicate URLs, 62 off-topic hits and
1 advert.

---

## Sentiment

Default is VADER with a **finance lexicon override** plus phrase collapsing, in
`services/sentiment_service.py`. Stock VADER is actively wrong on market
language — it reads "beat" as violence, has no opinion on "downgrade", and
scores "Boeing recalls 200K units after safety probe" as *positive*. The
override fixes the sign on all of those and needs no model download.

Multi-word phrases are collapsed to single tokens before scoring, because VADER
matches only whitespace-separated tokens and some phrases mean the opposite of
their parts: `dividend` is good news, `cuts dividend` is not.

FinBERT is still available and is better on nuanced text:

```bash
poetry install --extras finbert
STOCKY_SENTIMENT=finbert python main.py
```

If it is requested but cannot be loaded, the app logs and falls back rather
than failing a refresh.

---

## Project structure

```
stocky-backend/
├── main.py                    # FastAPI app (loopback only, CORS allow-list)
├── scheduler.py               # Background jobs, separate process
├── jobs.py                    # Refreshes, on-follow backfill, rollups
├── settings.py                # All configuration, env-driven
├── normalize.py               # Pure date/URL/title helpers (no I/O)
│
├── db/
│   ├── connection.py          # Schema + in-place migration, WAL
│   ├── stocks.py              # Catalogue and latest quote
│   ├── news.py                # Articles
│   ├── prices.py              # Daily bars + hourly snapshots
│   ├── watchlist.py           # The watchlist
│   ├── sentiment.py           # Daily rollups
│   └── summaries.py           # Cached AI digests
│
├── services/
│   ├── http_client.py         # The adaptive scraper everything shares
│   ├── yahoo.py               # Raw Yahoo endpoints, parsing only
│   ├── symbols.py             # Exchange hierarchy + resolution
│   ├── prices.py              # Quote/history with fallback chain
│   ├── dedup.py               # Relevance, clustering, story election
│   ├── sentiment_service.py   # Finance-tuned VADER, optional FinBERT
│   ├── ai_service.py          # Optional DeepSeek summaries
│   └── news/
│       ├── __init__.py        # Fan out, merge, store, score
│       ├── google_news.py     # RSS search + date-windowed backfill
│       ├── yahoo_news.py      # Search JSON + per-ticker RSS
│       ├── bing_news.py       # Second search index, links unwrapped
│       ├── finviz.py          # Quote-page news table
│       ├── nasdaq_news.py     # Per-ticker RSS (US)
│       ├── sec_edgar.py       # Material filings (US, opt-in)
│       ├── publishers.py      # Publisher name → domain
│       └── images.py          # og:image top-up, capped
│
├── routes/                    # stocks, news, watchlist, insights, system
└── tests/                     # 400 tests, no network
```

---

## Getting started

Python 3.12 (torch, if you enable FinBERT, has no 3.13+ wheels here).

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows
poetry install

python main.py                    # API on http://127.0.0.1:5000
python scheduler.py               # in a second terminal
```

Docs at `/docs`, and `/health` reports per-host scraper stats — the quickest way
to see whether a source is being throttled or has had its circuit opened.

The database migrates itself on start: an older `stocky.db` in the repo root is
moved to `data/stocky.db`, auth tables are dropped, per-user follows are folded
into the single watchlist, RFC-822 dates are rewritten to ISO 8601, and derived
keys are populated.

### Configuration

Everything has a working default; no key is required.

| Variable | Default | Purpose |
|---|---|---|
| `STOCKY_DB` | `data/stocky.db` | Database path |
| `STOCKY_HOST` / `STOCKY_PORT` | `127.0.0.1` / `5000` | Bind address |
| `STOCKY_CORS_ORIGINS` | localhost 3000/5173/8080 | Allow-list |
| `STOCKY_BACKFILL_DAYS` | `30` | History pulled for a new follow |
| `STOCKY_PRICE_REFRESH_OPEN_MINUTES` | `5` | Price cadence while any market is in session |
| `STOCKY_PRICE_REFRESH_MINUTES` | `60` | Price cadence once every market is shut |
| `STOCKY_QUOTE_STALE_MINUTES` | `15` | Serve a stored quote under this age, refresh it behind the response |
| `STOCKY_NEWS_REFRESH_MINUTES` | `60` | News cadence |
| `STOCKY_SENTIMENT` | `vader` | `vader` or `finbert` |
| `STOCKY_SEC_CONTACT` | — | Optional: an email address. Enables SEC EDGAR, which refuses requests that don't identify their caller |
| `DSEEK` | — | Optional: DeepSeek key for AI summaries |
| `212pk` / `212sk` | — | Optional: Trading212, only to refresh the catalogue |

---

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Status plus per-host scraper stats |
| POST | `/refresh` | Kick a full refresh in the background |
| GET | `/stocks/search?q=` | Search the catalogue |
| GET | `/stocks/popular` | Watchlist, topped up with best-covered stocks |
| GET | `/stocks/quotes?symbols=A,B` | Latest quotes |
| GET | `/stocks/{symbol}` | One stock |
| GET | `/stocks/{symbol}/prices?days=30` | Price series |
| GET | `/news` | Feed; defaults to the whole watchlist |
| GET | `/news/latest` | Newest headlines, for the ticker strip |
| GET | `/news/sources` | Article counts per publisher |
| GET | `/news/{id}` | One article |
| POST | `/news/{id}/ai-summary` | Summarise an article (needs `DSEEK`) |
| POST | `/news/stock/{symbol}/ai-summary` | Digest of recent coverage |
| GET | `/watchlist` | The watchlist with quotes |
| POST | `/watchlist` | Follow a stock; starts a month-long backfill |
| DELETE | `/watchlist/{symbol}` | Unfollow (keeps stored news) |
| PUT | `/watchlist/reorder` | Reorder |
| POST | `/watchlist/{symbol}/refresh` | Force a re-scrape |
| GET | `/insights/trending` | Most covered, most positive, negative shifts |
| GET | `/insights/movers` | Biggest price moves with sentiment shift |
| GET | `/insights/sentiment/{symbol}` | Daily sentiment series |

`/news` accepts `symbols`, `since`, `days`, `sentiment`, `relevance`, `limit`.

### Security

No authentication, which is exactly why the API binds to loopback and uses a
CORS allow-list rather than `*` — an unauthenticated API answering
`Access-Control-Allow-Origin: *` lets any page you visit read and modify your
watchlist. Symbols are validated against a ticker pattern before they reach a
query or an outbound scraper URL, all SQL is parameterised, and column names in
dynamic `UPDATE`s come from a whitelist.

---

## Background jobs

| Job | Schedule | Description |
|---|---|---|
| `refresh_prices` | Every 5m while a market is open, hourly otherwise | Quote + recent bars for followed stocks, refreshed concurrently |
| `refresh_news` | Hourly | New articles, images, sentiment |
| `aggregate_sentiment` | Daily 22:00 UTC | Rebuild daily rollups |
| `prune` | Daily 03:30 UTC | Retention |
| `refresh_catalogue` | Weekly | Trading212 instruments (needs keys) |
| `backfill_stock` | On follow | A month of prices and news |

---

## Tests

```bash
poetry run pytest            # 400 tests, no network access
```

Nothing in the suite touches a third party: the scraper is driven through
`httpx.MockTransport` with an injected clock, so the rate limiter, backoff and
circuit breaker are tested exactly and instantly. Parsers run against captured
payloads, and the API runs over a temporary SQLite file.

### Known limitations

- **Ambiguous one-word company names.** Relevance matching is keyword-based, so
  a company called "Shell" or "Apple" can pull in the occasional article that
  merely uses the word (~0.2% of a Shell backfill). Tightening it further costs
  more real articles than it saves, so it is left alone deliberately.
- **Publisher URLs from Google News** are not recovered (see above); those
  articles link via Google, which works but reduces their weight in dedup
  tie-breaks. Bing's links *are* unwrapped, so the same story arriving from
  both keeps the attributed copy.
- **History depends on Yahoo.** Nasdaq and CNBC cover quotes if Yahoo is down,
  but neither returns bars.
- **Market hours are approximate.** The fast/slow refresh gate uses weekday
  session windows with no exchange holiday calendar, so a public holiday costs
  one wasted refresh cycle. It can never produce a wrong price, only a
  redundant request.
- **US-only depth.** Finviz, Nasdaq and EDGAR are US listings only. A German or
  London line is covered by Google, Yahoo and Bing — for thin non-US tickers
  Bing is often the only one returning anything, which is why it was added.

---

## License

Private — all rights reserved.

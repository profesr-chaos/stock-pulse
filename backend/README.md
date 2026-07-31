# Stocky backend

News and prices for the stocks you follow, scraped from free public sources.
No API keys, no accounts, no subscription tiers — a single-user local tool.
FastAPI and SQLite.

Two things it has to do well:

1. **News** — one article per *story*, not fifty copies of the same wire
   report, keeping the most trustworthy outlet's version.
2. **Prices** — one canonical listing per company, in the currency it's
   actually quoted in, refreshed while its market is open, with a month of
   history behind it.

## Getting started

Python 3.12 (torch, if you enable FinBERT, has no 3.13+ wheels here).

```bash
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
poetry install

python main.py            # API on http://127.0.0.1:5000, docs at /docs
python scheduler.py       # second terminal, optional — background refreshes
```

The database migrates itself on start: an older `stocky.db` in the repo root
moves to `data/stocky.db`, dead auth tables are dropped, per-user follows fold
into the single watchlist, and RFC-822 dates are rewritten to ISO 8601.

`/health` reports per-host scraper stats — the quickest way to see whether a
source is being throttled or has had its circuit opened.

## How the data is obtained

Everything goes through `services/http_client.py`, one adaptive scraper shared
by every source. Per host it keeps a token bucket whose rate ratchets *up* while
responses stay clean and halves the moment a host answers 429/403/503. It obeys
`Retry-After`, retries with exponential backoff and full jitter, opens a circuit
breaker after repeated failures, and presents a stable browser fingerprint per
host. HTTP/2 and connection reuse are on, and a five-minute response cache means
several scrapers wanting the same feed in one refresh cost one request.

Not included: proxy rotation, or anything that defeats an access control rather
than sharing a host's capacity. Where a source pushes back, the answer is
another source.

### News

Seven fetches across five independent operators, queried concurrently, merged
and deduplicated — so no single company's outage takes the feed down. Spreading
the work is also what keeps it welcome: seven polite fetches across five
operators is far kinder to each than hammering one.

| Source | Why it's there | Caveat |
|---|---|---|
| Google News RSS | Broadest reach; the only one that can backfill a month | Opaque redirect links |
| Yahoo search JSON | The only free source of thumbnails that costs no extra request | Falls back to generic market news for thin tickers |
| Yahoo per-ticker RSS | Article summaries | Same fallback |
| Bing News RSS | A second search index, and the only one carrying thin non-US tickers | Needs its own query shape |
| Finviz quote page | Real publisher URLs, genuinely curated per ticker | US listings only |
| Nasdaq per-ticker RSS | Wire copy and editorial, on a host nothing else here touches | US only; returns generic news for unknown symbols, so it isn't trusted for `related` |
| SEC EDGAR Atom | The filing itself — the 8-K lands here before anyone reports on it | US only, opt-in |

**Bing needs a different query.** Google's
`"Company" OR "TICK stock" OR "TICK shares"` returns a full feed there and an
*empty* one on Bing, which answers a multi-term OR with zero items. Bing gets a
single quoted phrase plus the word `stock`, so the two can't share a query
builder. Its `apiclick.aspx` links carry the real URL in a query parameter, so
unwrapping is free — which means Bing items arrive with the publisher's own
domain and *win* dedup tie-breaks a Google copy of the same story would lose.

**Google's links stay wrapped.** Since the redirect format changed, the
`/rss/articles/CBMi…` payload is an opaque token, not base64, and recovering the
publisher's URL costs a POST per article. The token still redirects correctly in
a browser, so attribution comes from the feed's `<source>` element instead,
mapped to a domain in `services/news/publishers.py`.

**EDGAR is opt-in.** The SEC's fair-access policy requires a contact address in
the User-Agent and enforces it — a UA carrying a repo URL gets a flat 403, the
same request with an email returns 200. So the source switches on only when
`STOCKY_SEC_CONTACT` is set. Filed titles are useless as-is (`"8-K - Current
report"`), so titles are constructed from company name and form, and routine
insider paperwork (forms 3/4/5, 144) is filtered out.

**GDELT was tried and rejected.** Its worldwide index looks like the obvious way
to cover non-US listings, but the phrase search is too loose — `"shell"` returns
awards shows and retirement advice, and the precise form (`"Shell plc"`) appears
in almost no body copy. With a 20-second TLS handshake and a 429 at one request
per five seconds on top, it cost more latency per refresh than every other
source combined. Bing supplies the non-US reach it was added for.

### Prices

A fallback chain across three operators, so a throttled Yahoo means the next
source picks up rather than the refresh failing. Verified agreeing to the cent
on AAPL, RKLB and SHEL.L.

1. **Yahoo chart v8** — quote *and* daily history in one request, across two
   hostnames so a throttled one fails over.
2. **Nasdaq quote API** — US listings, real-time during the session. Refuses
   suffixed symbols on purpose: `SHEL.L` is the London ordinary, and Nasdaq
   would answer with the New York ADR at a different price in a different
   currency.
3. **CNBC quote API** — independent host, global coverage, accepts Yahoo-style
   symbols directly.

Nasdaq splits a quote into `primaryData` (whatever is trading now) and
`secondaryData` (the regular close once the bell goes). The regular-session
figure wins whenever present — taking the live block blindly would store an
after-hours print as the day's close and put a point on the chart neither other
source agrees with.

History comes from Yahoo only. If Yahoo is unavailable the quote still updates
from a fallback and stored history stops extending: degraded, not broken.

The scheduler ticks every five minutes but `jobs.refresh_prices` drops most of
those back to hourly once every market is shut — a closed market's price can't
move, so polling it is load on someone else's servers for an unchanged number.

## Exchange normalisation

The same company trades on many venues in many currencies, and the Trading212
catalogue is not a reliable guide to which one — it lists TSLA as an EUR
instrument. So listings are resolved against Yahoo search and ranked by exchange
in `services/symbols.py`:

```
US primary → London → XETRA → rest of western Europe → Canada
           → German regional → depositary receipts → everything else
```

The winner is confirmed to actually return a quote before being cached. Two
rules earn their keep:

- Local codes get a second search **by company name**: Trading212 calls Rocket
  Lab `6RJ0`, and only a name search surfaces `RKLB` on NASDAQ.
- LSE International Board tickers (they all start with a digit, e.g. `0NCA.L`)
  are demoted. Yahoo labels them plain "LSE", but they're cross-listings that
  barely trade — IVU's London line had 15 daily bars in a month where its XETRA
  line had 23.

Prices are always stored in **major** currency units. LSE quotes arrive in pence
and Tel Aviv in agorot, and a chart that silently mixes 3323.5 with 33.235 is
worse than no chart.

## Deduplication

Identity is a canonical URL hash with tracking parameters stripped, enforced by
a unique index. Near-duplicates are then clustered per stock within ±72 hours,
and each cluster elects a winner by source quality, then by whether it has an
image and a description. A duplicate isn't inserted — but any image or
description the stored row lacks is copied onto it.

Articles are tagged `direct` (names the stock) or `related` (sector context that
never names it), so the feed can separate them without discarding either.

On a fresh follow of Shell: **630 articles found → 418 stored**, having dropped
120 duplicate stories, 29 duplicate URLs, 62 off-topic hits and 1 advert.

## Sentiment

VADER with a finance lexicon override and phrase collapsing
(`services/sentiment_service.py`). Stock VADER is actively wrong on market
language: it reads "beat" as violence, has no opinion on "downgrade", and scores
"Boeing recalls 200K units after safety probe" as *positive*. The override fixes
the sign on all of those and needs no model download.

Multi-word phrases collapse to single tokens before scoring, because VADER
matches only whitespace-separated tokens and some phrases mean the opposite of
their parts — `dividend` is good news, `cuts dividend` is not.

FinBERT is better on nuanced text and still available:

```bash
poetry install --extras finbert
STOCKY_SENTIMENT=finbert python main.py
```

If it's requested but can't load, the app logs and falls back rather than
failing a refresh.

## Layout

```
main.py         FastAPI app — loopback only, CORS allow-list
scheduler.py    background jobs, separate process
jobs.py         refreshes, on-follow backfill, rollups
settings.py     all configuration, env-driven
normalize.py    pure date/URL/title helpers, no I/O

db/             one module per table; connection.py owns schema + migration
routes/         stocks, news, watchlist, insights, system
services/       http_client (the shared scraper), symbols, prices, dedup,
                sentiment_service, ai_service, news/ (one module per source)
tests/          428 tests, no network
```

## API

`/docs` has the full schema. The shape:

| Group | What's there |
|---|---|
| `/stocks` | Search the catalogue, quotes, one stock, its price series |
| `/news` | The feed (`symbols`, `since`, `days`, `sentiment`, `relevance`, `limit`), latest headlines, per-publisher counts, AI summaries |
| `/watchlist` | Follow, unfollow, reorder, force a re-scrape |
| `/insights` | Trending, movers, a stock's daily sentiment series |
| `/health`, `/refresh` | Scraper stats per host; kick a full refresh |

Following a stock starts a month-long backfill. Unfollowing keeps the news.

### Security

There's no authentication, which is exactly why the API binds to loopback and
uses a CORS allow-list rather than `*` — an unauthenticated API answering
`Access-Control-Allow-Origin: *` lets any page you visit read and modify your
watchlist. Symbols are validated against a ticker pattern before reaching a
query or an outbound URL, all SQL is parameterised, and column names in dynamic
`UPDATE`s come from a whitelist.

## Configuration

Everything has a working default. No key is required.

| Variable | Default | Purpose |
|---|---|---|
| `STOCKY_DB` | `data/stocky.db` | Database path |
| `STOCKY_HOST` / `STOCKY_PORT` | `127.0.0.1` / `5000` | Bind address |
| `STOCKY_CORS_ORIGINS` | localhost 3000/5173/8080 | Allow-list |
| `STOCKY_BACKFILL_DAYS` | `30` | History pulled for a new follow |
| `STOCKY_PRICE_REFRESH_OPEN_MINUTES` | `5` | Price cadence while a market is in session |
| `STOCKY_PRICE_REFRESH_MINUTES` | `60` | Price cadence once every market is shut |
| `STOCKY_QUOTE_STALE_MINUTES` | `15` | Serve a stored quote under this age, refresh behind the response |
| `STOCKY_NEWS_REFRESH_MINUTES` | `60` | News cadence |
| `STOCKY_SENTIMENT` | `vader` | `vader` or `finbert` |
| `STOCKY_SEC_CONTACT` | — | An email address; enables SEC EDGAR |
| `DSEEK` | — | DeepSeek key for AI summaries |
| `212pk` / `212sk` | — | Trading212, only to refresh the catalogue |

## Background jobs

| Job | Schedule | What it does |
|---|---|---|
| `refresh_prices` | 5m while a market is open, hourly otherwise | Quotes + recent bars, concurrently |
| `refresh_news` | Hourly | New articles, images, sentiment |
| `aggregate_sentiment` | Daily 22:00 UTC | Rebuild daily rollups |
| `prune` | Daily 03:30 UTC | Retention |
| `refresh_catalogue` | Weekly | Trading212 instruments (needs keys) |
| `backfill_stock` | On follow | A month of prices and news |

## Tests

```bash
poetry run pytest      # 428 tests, no network access
```

Nothing in the suite touches a third party. The scraper is driven through
`httpx.MockTransport` with an injected clock, so the rate limiter, backoff and
circuit breaker are tested exactly and instantly. Parsers run against captured
payloads; the API runs over a temporary SQLite file.

## Known limitations

- **Ambiguous one-word names.** Relevance matching is keyword-based, so a
  company called "Shell" or "Apple" pulls in the occasional article that merely
  uses the word (~0.2% of a Shell backfill). Tightening it costs more real
  articles than it saves, so it's left alone deliberately.
- **Google News links aren't unwrapped**, so those articles link via Google —
  which works, but weighs less in dedup tie-breaks. Bing's *are* unwrapped, so
  a story arriving from both keeps the attributed copy.
- **History depends on Yahoo.** Nasdaq and CNBC cover quotes if it's down,
  neither returns bars.
- **Market hours are approximate.** The fast/slow refresh gate uses weekday
  session windows with no holiday calendar, so a public holiday costs one wasted
  cycle. It can never produce a wrong price, only a redundant request.
- **US-only depth.** Finviz, Nasdaq and EDGAR are US listings only. A German or
  London line is covered by Google, Yahoo and Bing — and for thin non-US tickers
  Bing is often the only one returning anything.

## License

Private — all rights reserved.

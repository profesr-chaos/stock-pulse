# Stocky

News and prices for the handful of companies you actually follow, scraped from
free public sources. No accounts, no subscription tier, no required API key. It
runs on your own machine and the watchlist stays there.

The problem it solves is volume. Follow five stocks on any finance portal and
you get the same wire report fifty times, plus everything else the site wanted
to show you. Stocky merges seven fetches across five independent news operators,
collapses the copies of one story down to the best-attributed version, and
ranks what is left by how far the price moved. On a fresh follow of Shell that
was 630 articles found and 418 stored, after dropping 120 duplicate stories, 29
duplicate URLs, 62 off-topic hits and one advert.

Prices come from a three-source fallback chain, stored in major currency units,
and resolved to the listing the company actually trades on rather than whichever
line a catalogue happened to list first.

## Running it

You need Python 3.12, Node, and **Postgres 18 or newer**. The version floor is
real: surrogate keys default to the built-in `uuidv7()`, which arrived in 18 and
has no extension fallback. `docker compose up` in `backend/` brings its own.

```bash
createdb stocky

cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
poetry install
python main.py                  # API on :5000, docs at /docs
```

```bash
cd frontend
npm install
npm run dev                     # UI on :3000
```

A third terminal is optional:

```bash
cd backend && python scheduler.py    # background refreshes
```

Without the scheduler the UI still works. You just see whatever was last
scraped until you refresh a stock yourself.

Both ports are load-bearing. Vite is pinned to 3000, the frontend calls 5000,
and the backend's CORS allow-list names both. Change one in isolation and you
get a silent CORS failure that looks like an empty dashboard.

Tables are created on start, idempotently, so the API and the scheduler racing
each other is fine.

## Using it

Add a stock from the watchlist editor in the ticker strip. Following one kicks
off a month-long backfill of prices and news, so the feed fills in behind you
rather than making you wait. Unfollowing keeps the articles.

The page is one screen. Trending leads, Latest runs beside it, the news river
picks up underneath, and the right rail holds tickers. Clicking a ticker
anywhere filters everything to that stock. The search bar filters by text, date
window, sentiment and relevance, and a search collapses the layout to a single
ranked list.

Pinning a ticker in the rail is session state on purpose. It is a temporary look
at a quote, not a decision to start scraping something.

Articles open in a reader dialog with whatever description was published. Many
arrive as a Google News redirect with nothing behind them, so there is a
"Summarise with AI" button rather than a body that is blank half the time. That
button costs nothing until you click it.

The backend pushes a message over `/ws` whenever it commits anything, so a
scheduler refresh or an edit in another tab updates the open page without a
reload.

## The optional LLM

Stocky is a scraper first. The LLM adds two things, both switchable from the AI
settings dialog in the ticker strip, and neither is load-bearing.

| Toggle | What it costs | What you lose by turning it off |
|---|---|---|
| Grade new articles during scraping | One API call per stock per refresh, only on refreshes that inserted something | The high/medium/low impact tags on article cards |
| AI summaries on demand | One call per click | The summarise button on articles and stocks |

The grading call asks one question: would an investor who already read the last
week's coverage learn anything materially new here? The database is the prior.
There is no vector store and no knowledge base, because what is already stored
is what the reader already knows. Zero events is the normal answer, not a
failure.

The two flags are deliberately separate. Someone who wants to stop the silent
background spend usually still wants the summarise button to work.

Turning grading off changes the scrape by exactly nothing else. Verified against
the live scrapers rather than the stubs: 268 articles found with the LLM off and
268 with it on. Articles stored while grading is off keep their impact NULL, not
`low`, so a later refresh can still tier them. NULL means never judged and `low`
means judged and unremarkable, and collapsing the two would lose that
distinction permanently.

Set `DSEEK` to a DeepSeek key to enable any of it. Without a key both toggles
say so in the dialog instead of pretending to work. A key the provider rejects
with 401 or 403 latches off after the first failure, since an expired key
otherwise made every stock in every hourly refresh pay a full round trip to be
told 401 again. Rate limits and server errors do not latch, because those are
worth retrying. Fix the key and restart the backend to re-arm.

The masthead flickers RGB while grading is actually running and sits flat black
when it is not. It is driven by the effective state rather than the flag, so it
cannot claim to be spending tokens it has no usable key for.

## How it compares

Against a finance portal: one row per story instead of every syndicated copy,
only the companies you follow, and a page with nothing on it you did not ask
for. Against a paid data feed: no key, no quota, no bill, at the cost of
depth. Against both: the watchlist is a table in your own Postgres.

The trade you are making is coverage guarantees. Scraped sources can throttle,
change shape or go down, which is why news comes from five operators and prices
from three, with fallbacks between them. Something being unavailable degrades
the feed rather than emptying it.

US listings get the most depth, since Finviz, Nasdaq and SEC EDGAR are US only.
A London or German line is covered by Google, Yahoo and Bing, and for thin
non-US tickers Bing is often the only source returning anything.

## Recent changes

- The LLM became optional rather than assumed, with per-feature toggles stored
  in the database and a rejected key that stops costing time.
- Articles are graded for impact against the coverage already stored, and the
  tier shows on the card.
- Zero-information churn is dropped at ingest, before it can reach a prompt.
- Storage moved from SQLite to Postgres. `backend/import_sqlite.py` carries an
  old `data/stocky.db` across, once, into an empty database.
- A WebSocket push channel replaced polling for cache invalidation.

## Where the detail lives

| Path | Stack | Read |
|---|---|---|
| `backend/` | FastAPI, Postgres, psycopg 3, raw SQL | [backend/README.md](backend/README.md) |
| `frontend/` | Vite, React, TypeScript, Tailwind | [frontend/README.md](frontend/README.md) |

The backend README covers every source and why it is there, the shared scraper's
rate limiting and circuit breaking, exchange normalisation, deduplication,
sentiment, and the full environment variable table. The frontend README covers
the data path and the deliberate absences (no router, no component library, no
theme provider).

There is no workspace tool here, no npm workspaces or turbo, and no root
`package.json`. The backend is Python, so a JS workspace would only ever wrap
half the repo. Add one the day a genuinely shared JS package appears.

## Git history

Both apps lived in separate repos until `git subtree` grafted them in, so
commits from before the graft record the old paths (`main.py`, not
`backend/main.py`). In practice:

- `git blame backend/main.py` works fine and traverses the whole history.
- `git log -- backend/main.py` **stops at the graft.** Pass both paths:
  `git log -- backend/main.py main.py`, or `git log -- frontend/src src`.
- `git log --follow` does not cross the graft at all.

The pre-monorepo checkouts are parked in `..\stocky-legacy\`. Nothing there is
live. It also holds a dead frontend copy from a different repo that happens to
share this one's name, so don't mistake it for this code.

## License

Private, all rights reserved.

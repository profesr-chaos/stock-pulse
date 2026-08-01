# Stocky

Best way to get free and simple news and prices for the handful of companies you actually follow, pulled from
free public sources. No API keys, no accounts, no subscription tiers — it runs
on your own machine and answers to you.

Two apps, one repo. They share no build tooling; they only meet over HTTP.

| Path | What it is | Runs on |
|---|---|---|
| [`backend/`](backend/) | FastAPI + Postgres. Scrapes, deduplicates, scores, serves. | `127.0.0.1:5000` |
| [`frontend/`](frontend/) | Vite + React + TypeScript. One screen, no router. | `127.0.0.1:3000` |

Each has its own README with the detail that matters for working in it.

## Running it

Two terminals:

```bash
cd backend   && .venv/Scripts/python.exe main.py   # API + docs at /docs
cd frontend  && npm run dev                        # UI at :3000
```

A third, optional, for background refreshes: `python scheduler.py`. The UI works
without it — you just get whatever was last scraped until you hit refresh.

Both ports are load-bearing. Vite is pinned to 3000, the frontend calls port
5000, and the backend's CORS allow-list names both. Change one in isolation and
you get a silent CORS failure that looks like an empty dashboard.

## Why there's no workspace tool

No npm workspaces, no turbo, no root `package.json`. The backend is Python, so
a JS workspace would only ever wrap half the repo — all config and no shared
anything. Add one the day a genuinely shared JS package appears.

## Git history

Both apps lived in separate repos until `git subtree` grafted them in, so
commits from before the graft record the *old* paths (`main.py`, not
`backend/main.py`). In practice:

- `git blame backend/main.py` — fine, traverses the whole history.
- `git log -- backend/main.py` — **stops at the graft.** Pass both paths:
  `git log -- backend/main.py main.py`, or `git log -- frontend/src src`.
- `git log --follow` doesn't cross the graft at all.

The pre-monorepo checkouts are parked in `..\stocky-legacy\`. Nothing there is
live. It also holds a dead frontend copy from a *different* repo that happens to
share this one's name — don't mistake it for this code.

## License

Private — all rights reserved.

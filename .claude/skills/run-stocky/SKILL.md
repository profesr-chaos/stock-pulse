---
name: run-stocky
description: Launch and drive the Stocky app — FastAPI backend plus Vite/React frontend — to see a change working in the real UI. Use when asked to run, start, serve, or screenshot Stocky, or to confirm a change works end to end rather than only in tests.
---

# Running Stocky

Two processes, one repo, no Docker needed for local work.

| Part | Directory | Command | URL |
|---|---|---|---|
| Backend | `backend` | `.venv/Scripts/python.exe main.py` | http://127.0.0.1:5000 |
| Frontend (dev) | `frontend` | `npm run dev` | http://127.0.0.1:3000 |
| Frontend (built) | `frontend` | `npm run build && npm run serve` | http://127.0.0.1:4173 |

Both ports are load-bearing. `vite.config.ts` pins the frontend to `127.0.0.1:3000`,
the frontend calls `http://127.0.0.1:5000` from `src/config/api.ts` (override with
`VITE_API_URL`, which `.env` sets), and the backend's CORS allow-list names ports 3000
and 4173. Change one and you get a silent CORS failure that looks like an empty
dashboard.

`npm run serve` is a stdlib Node static server (`scripts/serve-dist.mjs`) that does
Brotli/gzip negotiation and immutable cache headers — `vite preview` sends everything
uncompressed, so it cannot show what the bundle actually costs. **Measure Lighthouse
against 4173, never against the dev server**: dev serves unminified ES modules and
scores meaninglessly low.

## Launch

Start both in the background, then wait for their ready lines rather than sleeping:

```bash
# backend  (from backend/)
.venv/Scripts/python.exe main.py

# frontend (from frontend/)
npm run dev
```

```bash
# wait for ready — match failure strings too, or a crash looks like "still starting"
until grep -qiE "Application startup complete|Traceback|Error" "$BACKEND_LOG"; do sleep 1; done
until grep -qiE "ready in|Local:|error|EADDRINUSE" "$FRONTEND_LOG"; do sleep 1; done
```

To hand the user terminals they can actually read, launch tabs rather than background
jobs — `Start-Process powershell` from an agent session creates a **windowless** console
with no visible output:

```powershell
$py = 'C:\Users\adamg\stocky\backend\.venv\Scripts\python.exe'
Start-Process wt.exe -ArgumentList "new-tab --title `"Stocky API`" -d `"$be`" powershell -NoExit -Command `"& '$py' main.py`""
```

Two traps in that one line: **`wt` eats `;` as its own tab separator**, so a
`-Command "cd x; y"` silently splits into two broken tabs — use `-d` for the directory
and keep the command semicolon-free. And invoke the interpreter through `&` with an
absolute path; a bare `.venv\Scripts\python.exe` fails to resolve in the new tab.

`scheduler.py` is a **separate optional process**. It is not needed to view the app —
the API refreshes stale quotes on request and `POST /refresh` covers manual runs.
Start it only when testing the cron cadence itself.

## Drive it

Launching proves the entrypoint resolves. To prove the data layer works:

```bash
curl -s http://127.0.0.1:5000/health          # watchlist, article counts, per-host scraper stats
curl -s -X POST http://127.0.0.1:5000/refresh # full pipeline: prices + news for every followed stock
```

`/refresh` returns `{"ok":true}` immediately and runs in a FastAPI background task —
watch the backend log for `[prices] N updated` and `[news] refresh complete`. On a
12-stock watchlist it takes a few minutes and fetches roughly 2,000 articles.

Verify what landed by source rather than trusting the counts:

```bash
cd backend && .venv/Scripts/python.exe -c "
import sqlite3; c=sqlite3.connect('data/stocky.db')
for r in c.execute(\"SELECT source_type, COUNT(*) FROM news WHERE created_at > datetime('now','-1 day') GROUP BY 1 ORDER BY 2 DESC\"): print(r)
"
```

## Screenshot the UI

There is no Playwright or chromium-cli here. Use the installed Chrome headless:

```bash
"C:/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1600,2200 --virtual-time-budget=12000 \
  --screenshot="$OUT/app.png" http://127.0.0.1:3000/
```

`--virtual-time-budget` is required: the dashboard fetches through TanStack Query, so
a shorter budget captures an empty shell. **Read the PNG afterwards** — a dark blank
frame means the API call failed, not that the app is styled minimally. The `GCM
registration` errors Chrome prints are harmless.

## Gotchas

- **Use `.venv/Scripts/python.exe` directly.** The venv is not auto-activated.
- **Killing the uvicorn *reloader* orphans its worker, which keeps port 5000.**
  `main.py` runs with `reload=True`, so there are two processes: a StatReload parent
  and a `multiprocessing.spawn` worker that owns the socket. Kill only the parent and
  the worker survives, still serving the code it started with. `netstat` keeps listing
  the *parent's* PID, so `Get-Process -Id` on it reports "cannot find a process" and it
  looks like an unkillable zombie socket. It is not — the worker is a live process:

  ```powershell
  # every python worker whose parent is gone == an orphaned server
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'multiprocessing-fork' -and
                   -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  ```

  Filtering processes by `CommandLine -match 'stocky'` **will not find these** — the
  worker's command line is bare `multiprocessing.spawn`, with no project path in it.
  More than one `:5000 LISTENING` row means orphans are stacked up and Windows is
  splitting requests between them; the symptom is an edit that takes on some requests
  and not others. Reboot is never needed.
- **`PYTHONPATH=.` for standalone scripts.** Anything importing `services`/`db` outside
  pytest fails with `ModuleNotFoundError: No module named 'services'` without it.
- **`.env` changes need a full restart.** `main.py` runs uvicorn with `reload=True`, but
  StatReload watches `.py` files only — editing `.env` silently keeps the old value.
  Kill and relaunch to pick up e.g. `STOCKY_SEC_CONTACT`.
- **One repo.** `stocky` is a monorepo: `backend/` (FastAPI) and `frontend/` (Vite).
  The pre-monorepo checkouts and the stale `stock-pulse` copy were moved to
  `C:\Users\adamg\stocky-legacy\`; nothing there is live.

## Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest -q   # ~430 tests, no network
cd frontend && npm test                              # vitest
```

The backend suite never touches a third party — the scraper runs through
`httpx.MockTransport` with an injected clock. If a test starts making real requests,
something lost its monkeypatch.

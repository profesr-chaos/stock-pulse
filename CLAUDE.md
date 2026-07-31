# Stocky — monorepo

Free stock news + price aggregator. Two apps, one repo, no shared build tooling
between them — they only meet over HTTP.

Remote: `profesr-chaos/stock-pulse` (the repo is named for the frontend package,
which predates the merge; the project is Stocky).

| Path | Stack | Run from that dir |
|---|---|---|
| `backend/` | FastAPI + SQLite | `.venv/Scripts/python.exe main.py` → :5000 |
| `frontend/` | Vite + React + TS | `npm run dev` → :3000 |

Each has its own `CLAUDE.md` with the detail that matters for working in it —
read the one for the side you're touching. The `run-stocky` skill in
`.claude/skills/` covers launching both and the port/CORS traps.

No workspace tool (npm workspaces, turbo, nx) and no root `package.json`: the
backend is Python, so a JS workspace would only ever wrap one of the two. Add
one if a genuinely shared JS package appears.

## Git history

Both apps were separate repos until they were grafted in with `git subtree`,
so commits before the graft record the *old* paths (`main.py`, not
`backend/main.py`). Consequences:

- `git blame backend/main.py` — works normally, traverses the whole history.
- `git log -- backend/main.py` — **stops at the graft merge.** Pass both the new
  and old path to see everything: `git log -- backend/main.py main.py`, or
  `git log -- frontend/src src`.
- `git log --follow` does not work across the graft at all.

The pre-monorepo checkouts are parked in `..\stocky-legacy\`. Nothing there is
live; delete once you trust this repo. It also holds a dead parallel frontend
copy from `AdamTweedie/stock-pulse` — **a different repo that happens to share
this one's name**, last touched April 2026, with a `USE_MOCK_DATA` flag and dead
`/auth` URLs. Don't confuse it with the `profesr-chaos/stock-pulse` remote above.

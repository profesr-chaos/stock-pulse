# Stocky — monorepo

Free stock news + price aggregator. Two apps, one repo, no shared build tooling
between them — they only meet over HTTP.

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

The pre-monorepo checkouts are parked in `..\stocky-legacy\` (also the stale
`stock-pulse` prototype — a dead parallel copy, not a third app). Nothing there
is live; delete once you trust this repo.

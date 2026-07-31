# Stocky backend — agent context

Free stock news + price aggregator. Scrapers only, no paid APIs, no auth.
FastAPI + SQLite.

`.mulch/` is the predecessor knowledge store (`ml`), left in place and not
migrated to marl.

<!-- marl:start -->
## marl — this project's knowledge store

Run `marl prime` at session start and treat the output as project ground truth.

- **Before recording:** `marl search <keywords>` — if the fact already exists, `marl confirm <id>` instead of duplicating it.
- **Before finishing a task:** record non-obvious learnings — `marl record <domain> "<text>" --type convention|pattern|failure|decision|note`.
- **When a primed record proves correct in practice:** `marl confirm <id>`. Confirm means "I applied this and it held", not "I read it" — confirming everything you prime destroys the signal that keeps knowledge alive.
- **When a primed record proves wrong:** `marl revise <id> "<corrected text>"`. Never record a contradicting fact alongside the old one. If it no longer applies at all, `marl drop <id> "<reason>"`.
- **When committing:** include `.marl/` in the same commit as the change that produced the learning.

One fact per record, written so a stranger can act on it without context: gotchas with their resolution (`failure`), choices with their reason (`decision`), "always do X here" rules (`convention`), reusable approaches (`pattern`). Do not record anything derivable by reading the code, session-specific state, secrets, or restatements of the task.

Domains are short, stable, lowercase labels (`db`, `api`, `auth`, `build`). Reuse an existing one before inventing a new one.
<!-- marl:end -->

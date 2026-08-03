"""One-off: turn the stored catalogue into a seed file of primary listings.

Every row is resolved against Yahoo through `services.symbols.resolve`, which
ranks the candidate listings by exchange and then confirms the winner actually
returns a quote. So the output carries Yahoo's symbols and names rather than
whatever local code the row started with — `CHV` becomes `CVX`, `6RJ0` becomes
`RKLB` — and many rows collapse onto one instrument on the way.

The broker's own codes do not survive: they are the input, and every field in
the output is Yahoo's. That is what makes the result shareable — see
`write_json`.

Deliberately slow, and `--rate` is the knob that matters, not `--workers`.
Yahoo publishes no limit for these endpoints, so the sustainable rate is
empirical; 1/s per host is the conservative starting point. Every answer is
appended to `data/catalogue_progress.jsonl` as it arrives, so killing this and
re-running it resumes rather than starting over.

    python build_catalogue.py                 # the whole catalogue, 1 req/s/host
    python build_catalogue.py --limit 800     # a sample, to calibrate --rate
    python build_catalogue.py --rate 2.0      # once a rung has proven clean
    python build_catalogue.py --json-only     # rebuild the seed from progress

Run it with `STOCKY_SCRAPE_MAX_RETRIES=1`. At the default 3, a single throttled
URL produces four consecutive failures on its own — one short of the scraper's
circuit-breaker threshold.
"""
from __future__ import annotations

import argparse
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import db
from services import http_client, symbols

HERE = Path(__file__).resolve().parent
PROGRESS = HERE / "data" / "catalogue_progress.jsonl"
OUTPUT = HERE / "seed" / "catalogue.json"

_YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")

# `resolve` accepts a name match of 55, which is right when you are resolving
# one known stock and can eyeball the answer. This sweep is unattended and its
# output ships, so a non-exact ticker has to look much more like the same
# company before it is believed.
NAME_FLOOR = 85

# Types worth seeding: what the price and news pipeline can actually work with.
KEEP_TYPES = frozenset({"STOCK", "ETF", "FUND", "INDEX"})

_progress_lock = threading.Lock()


def pending(done: dict, limit: int | None) -> list[dict]:
    """Catalogue rows still needing an answer, minus the ones not worth asking.

    Leveraged and inverse wrappers are dropped here rather than after
    resolution: `_looks_derivative` is the same test resolution uses to avoid
    matching an ETP to its underlying, and there is no point spending a lookup
    on a row that should not be in a seed file at all.
    """
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT short_name, name FROM stocks ORDER BY short_name")]

    # Only successes count as done. A miss is usually transient — Yahoo
    # throttles, the scraper's circuit opens, and every lookup behind it comes
    # back empty — so treating misses as permanent poisons the run that
    # recorded them and every resume after it. Re-asking about a genuinely dead
    # ticker is much cheaper than silently losing thousands of live ones.
    resolved_already = {k for k, v in done.items() if v.get("resolved")}
    rows = [r for r in rows
            if r["name"] and not symbols._looks_derivative(r["name"])
            and r["short_name"] not in resolved_already]
    if not limit:
        return rows
    # A trial run has to be a random sample, not the first N. The catalogue is
    # ordered by symbol, so the head of it is entirely numeric-prefixed European
    # codes (`02G`, `100H`, `123F`) — a slice of that says nothing about how the
    # sweep will do on the tickers anyone actually searches for.
    return random.Random(0).sample(rows, min(limit, len(rows)))


def load_progress() -> dict[str, dict]:
    if not PROGRESS.exists():
        return {}
    records = {}
    with PROGRESS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue          # half-written line from a hard kill
            records[record["short_name"]] = record
    return records


def wait_out_circuit(timeout: float = 900.0) -> None:
    """Block while a Yahoo host's breaker is open.

    An open breaker answers instantly with `None`, so without this a throttle
    burns `MISS_STREAK_ABORT` rows in milliseconds and aborts a six-hour run
    over what is really a 45-second cooldown. Waiting turns a throttle into a
    pause and writes no phantom misses while it lasts.
    """
    waited = 0.0
    while waited < timeout:
        if not any(h["circuit_open"] for h in http_client.scraper.stats()):
            return
        print(f"[build] circuit open, waiting ({waited:.0f}s so far)", flush=True)
        time.sleep(15.0)
        waited += 15.0


def resolve_one(row: dict, handle) -> dict:
    """Resolve one row and checkpoint the answer, including the failures.

    A miss is recorded too, otherwise every re-run pays for the same hopeless
    lookups again.
    """
    wait_out_circuit()
    resolved = None
    try:
        result = symbols.resolve(row["short_name"], row["name"])
        if result:
            resolved = {
                "symbol": result["symbol"],
                "name": result["name"],
                "quote_type": result["quote_type"],
                "currency": result.get("currency"),
                "exchange": result.get("exchange"),
                "rank": result["rank"],
                "name_score": result["name_score"],
                "exact_symbol": result["exact_symbol"],
            }
    except Exception as exc:      # one bad row must not stop the sweep
        print(f"[build] {row['short_name']} errored: {type(exc).__name__}: {exc}")

    record = {"short_name": row["short_name"], "name": row["name"], "resolved": resolved}
    with _progress_lock:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
    return record


# A throttled Yahoo answers everything with nothing, and the sweep cannot tell
# that from a row that genuinely has no listing. This many misses in a row means
# it is the connection, not the data: stop and let someone lower --workers
# rather than burn through 14k rows recording garbage.
MISS_STREAK_ABORT = 40


class Throttled(RuntimeError):
    pass


def sweep(rows: list[dict], workers: int) -> None:
    """Resolve every row, stopping early if Yahoo starts refusing.

    Not a `with ThreadPoolExecutor(...)` block: `map` submits every task up
    front and the context manager waits for all of them on the way out, so
    raising inside the loop stops *reading* results while thousands of queued
    lookups carry on recording misses. The stop flag short-circuits whatever is
    already in flight and `cancel_futures` drops the rest.
    """
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    done = hits = streak = 0
    stop = threading.Event()

    with PROGRESS.open("a", encoding="utf-8") as handle:
        def work(row: dict) -> dict | None:
            return None if stop.is_set() else resolve_one(row, handle)

        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="build")
        try:
            for record in pool.map(work, rows):
                if record is None:
                    continue                  # cancelled, not an answer
                done += 1
                if record["resolved"]:
                    hits += 1
                    streak = 0
                else:
                    streak += 1
                    if streak >= MISS_STREAK_ABORT:
                        stop.set()
                        raise Throttled(
                            f"{streak} misses in a row after {done} rows — Yahoo is "
                            f"almost certainly throttling. Resolved rows are already "
                            f"checkpointed; re-run later to continue."
                        )
                if done % 250 == 0:
                    print(f"[build] {done}/{len(rows)}, {hits} resolved "
                          f"({100 * hits / done:.0f}%)", flush=True)
                    print_scraper_stats()
        finally:
            stop.set()
            pool.shutdown(wait=False, cancel_futures=True)
            print_scraper_stats()


def print_scraper_stats() -> None:
    """The four numbers a calibration run is judged on. `throttled` above zero
    or a rate below the one asked for means the rung was too fast."""
    for host in http_client.scraper.stats():
        print(f"[build]   {host['host']}: {host['requests']} req, "
              f"{host['throttled']} throttled, {host['failures']} failed, "
              f"{host['rate_per_sec']}/s"
              f"{' CIRCUIT OPEN' if host['circuit_open'] else ''}", flush=True)


def write_json(records: dict[str, dict]) -> dict:
    """Best row per resolved symbol, written as the seed file.

    Several local codes reach the same instrument — six WisdomTree lines, one
    fund — so the resolved symbol is the deduplication key, and the candidate
    with the best exchange rank wins it. That collapse is also what makes the
    output publishable: the key is Yahoo's symbol, every field written is
    Yahoo's, and the broker code each row started life as exists only in the
    local progress file.
    """
    best: dict[str, dict] = {}
    stats = {"records": len(records), "no_listing": 0, "low_confidence": 0,
             "wrong_type": 0, "merged": 0}

    for record in records.values():
        resolved = record.get("resolved")
        if not resolved:
            stats["no_listing"] += 1
            continue
        if not (resolved["exact_symbol"] or resolved["name_score"] >= NAME_FLOOR):
            stats["low_confidence"] += 1
            continue

        quote_type = (resolved["quote_type"] or "").upper()
        instrument_type = symbols._CATALOGUE_TYPE.get(quote_type, quote_type)
        if instrument_type not in KEEP_TYPES:
            stats["wrong_type"] += 1
            continue

        candidate = {
            "symbol": resolved["symbol"],
            "name": resolved["name"],
            "type": instrument_type,
            "currency": resolved.get("currency") or "",
            "_rank": resolved["rank"],
            "_score": resolved["name_score"],
        }
        held = best.get(candidate["symbol"])
        if held:
            stats["merged"] += 1
            if (held["_rank"], -held["_score"]) <= (candidate["_rank"], -candidate["_score"]):
                continue
        best[candidate["symbol"]] = candidate

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = [{k: best[s][k] for k in ("symbol", "name", "type", "currency")}
            for s in sorted(best)]
    with OUTPUT.open("w", encoding="utf-8") as fh:
        # One instrument per line. Still a plain JSON array, but a regenerated
        # file diffs row by row instead of as one 10,000-symbol blob.
        fh.write("[\n")
        fh.write(",\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
        fh.write("\n]\n")

    stats["written"] = len(best)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4,
                        help="only hides latency; --rate is the throttle")
    parser.add_argument("--rate", type=float, default=1.0,
                        help="requests per second per Yahoo host")
    parser.add_argument("--limit", type=int, default=None,
                        help="resolve at most this many rows, for a trial run")
    parser.add_argument("--json-only", action="store_true",
                        help="skip the sweep, just rebuild the seed from progress")
    args = parser.parse_args()

    # Pin both hosts to --rate at start *and* ceiling. Capping only the ceiling
    # would leave Yahoo starting at 4/s and coming down only via a throttle —
    # the exact event this exists to avoid. Must happen before the first
    # request, since `_state` reads these once per host.
    for host in _YAHOO_HOSTS:
        http_client._HOST_RATES[host] = (args.rate, args.rate)

    done = load_progress()
    print(f"[build] {len(done)} already resolved in {PROGRESS.name}")

    if not args.json_only:
        rows = pending(done, args.limit)
        print(f"[build] {len(rows)} to go, {args.workers} workers "
              f"at {args.rate}/s per host")
        try:
            if rows:
                sweep(rows, args.workers)
        except Throttled as exc:
            print(f"[build] STOPPED: {exc}")
        done = load_progress()

    stats = write_json(done)
    print(f"[build] {OUTPUT}: {stats.pop('written')} instruments")
    print(f"[build] dropped {stats}")


if __name__ == "__main__":
    main()

"""The instrument catalogue and its latest quote."""
from __future__ import annotations

from normalize import now_iso

from .connection import get_connection, one, rows

_ALLOWED_UPDATE_FIELDS = frozenset({
    "name", "type", "currency_code", "industry", "sector",
    "yahoo_symbol", "exchange", "quote_currency", "resolved_at",
    "price", "price_change", "price_change_percent", "price_updated_at",
})


# ── Read ─────────────────────────────────────────────────────────────────

def get_stock(short_name: str) -> dict | None:
    with get_connection() as conn:
        return one(conn.execute("SELECT * FROM stocks WHERE short_name = ?", (short_name,)))


def get_stocks(short_names: list[str]) -> list[dict]:
    if not short_names:
        return []
    marks = ",".join("?" * len(short_names))
    with get_connection() as conn:
        found = rows(conn.execute(f"SELECT * FROM stocks WHERE short_name IN ({marks})", short_names))
    # preserve caller order
    by_name = {s["short_name"]: s for s in found}
    return [by_name[n] for n in short_names if n in by_name]


def search_stocks(query: str, limit: int = 25) -> list[dict]:
    """Symbol-first ranking: exact, then symbol prefix, then name prefix, then
    name substring. A LIKE scan over ~15k rows is well under a millisecond, so
    no FTS table to keep in sync.

    Ties break towards the primary listing and away from derivatives: searching
    "tesla" should surface TSLA, not the German TL0 line or a 3x short ETP.
    """
    q = (query or "").strip()
    if not q:
        return []
    prefix, contains = f"{q}%", f"%{q}%"
    with get_connection() as conn:
        return rows(conn.execute("""
            SELECT * FROM stocks
            WHERE short_name LIKE ? OR name LIKE ?
            ORDER BY
                CASE
                    WHEN short_name = ?    THEN 0
                    WHEN short_name LIKE ? THEN 1
                    WHEN name LIKE ?       THEN 2
                    ELSE 3
                END,
                CASE WHEN type = 'STOCK' THEN 0 ELSE 1 END,
                -- already resolved to a US line? that's the primary listing
                CASE WHEN exchange IN ('NMS','NYQ','NGM','NCM','ASE','PCX','BTS') THEN 0 ELSE 1 END,
                -- secondary European lines usually carry digits (TL0, NVD2, 6RJ0)
                CASE WHEN short_name GLOB '*[0-9]*' THEN 1 ELSE 0 END,
                LENGTH(name),
                LENGTH(short_name) DESC,
                short_name
            LIMIT ?
        """, (prefix, contains, q.upper(), prefix, prefix, limit)))


def get_sectors(short_names: list[str] | None = None) -> list[dict]:
    """Sectors available to filter by, at both of Yahoo's levels.

    Neither level works alone. `sector` is eleven buckets wide, so Rocket Lab
    sits in "Industrials" next to a lift manufacturer — useless for "show me
    space stocks". `industry` is precise ("Aerospace & Defense") but so narrow
    that a twelve-stock watchlist produces ten filters holding one stock each.

    So both are returned, tagged with `level`, and symbols_in_sector() matches
    either column. Broad browsing and precise filtering out of one list.
    """
    if short_names is not None and not short_names:
        return []

    scope, params = "", []
    if short_names is not None:
        marks = ",".join("?" * len(short_names))
        scope = f"AND short_name IN ({marks})"
        params = list(short_names)

    with get_connection() as conn:
        return rows(conn.execute(f"""
            SELECT sector AS sector, 'group' AS level, NULL AS group_name,
                   COUNT(*) AS stock_count
            FROM stocks
            WHERE sector IS NOT NULL AND sector != '' {scope}
            GROUP BY sector

            UNION ALL

            SELECT industry AS sector, 'industry' AS level, MIN(sector) AS group_name,
                   COUNT(*) AS stock_count
            FROM stocks
            WHERE industry IS NOT NULL AND industry != '' {scope}
            GROUP BY industry

            ORDER BY stock_count DESC, level, sector
        """, [*params, *params]))


def symbols_in_sector(sector: str, short_names: list[str] | None = None) -> list[str]:
    """Which of these stocks belong to a sector. Matches the coarse `sector`
    column too, so "Industrials" works as well as "Aerospace & Defense"."""
    if not sector:
        return []
    where = ["(industry = ? OR sector = ?)"]
    params: list = [sector, sector]
    if short_names is not None:
        if not short_names:
            return []
        where.append(f"short_name IN ({','.join('?' * len(short_names))})")
        params += short_names

    with get_connection() as conn:
        return [r["short_name"] for r in conn.execute(
            f"SELECT short_name FROM stocks WHERE {' AND '.join(where)}", params
        )]


def count_stocks() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM stocks").fetchone()["c"]


def get_unresolved(short_names: list[str]) -> list[dict]:
    """Watchlist entries whose best listing has never been resolved."""
    if not short_names:
        return []
    marks = ",".join("?" * len(short_names))
    with get_connection() as conn:
        return rows(conn.execute(
            f"SELECT * FROM stocks WHERE short_name IN ({marks}) AND yahoo_symbol IS NULL",
            short_names,
        ))


# ── Write ────────────────────────────────────────────────────────────────

def bulk_upsert_stocks(stocks: list[dict]) -> int:
    """Insert new instruments, refresh names on existing ones. Returns inserts."""
    if not stocks:
        return 0
    payload = [
        (s["shortName"], s["name"], s["type"], s.get("currencyCode"))
        for s in stocks
        if s.get("shortName") and s.get("name") and s.get("type")
    ]
    with get_connection() as conn:
        before = conn.execute("SELECT COUNT(*) AS c FROM stocks").fetchone()["c"]
        conn.executemany("""
            INSERT INTO stocks (short_name, name, type, currency_code)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(short_name) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                currency_code = COALESCE(excluded.currency_code, stocks.currency_code)
        """, payload)
        after = conn.execute("SELECT COUNT(*) AS c FROM stocks").fetchone()["c"]
    return after - before


def upsert_stock(short_name: str, name: str, type: str = "STOCK", currency_code: str | None = None) -> None:
    """Used when a symbol is followed that isn't in the catalogue yet."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO stocks (short_name, name, type, currency_code)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(short_name) DO UPDATE SET name = excluded.name
        """, (short_name, name, type, currency_code))


def update_stock(short_name: str, **fields) -> bool:
    """Update whitelisted columns. The whitelist keeps caller-supplied keys out
    of the SQL string."""
    fields = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE stocks SET {set_clause} WHERE short_name = ?",
            [*fields.values(), short_name],
        )
        return cur.rowcount > 0


def set_resolution(short_name: str, yahoo_symbol: str, exchange: str | None, quote_currency: str | None) -> None:
    with get_connection() as conn:
        conn.execute("""
            UPDATE stocks
            SET yahoo_symbol = ?, exchange = ?, quote_currency = ?, resolved_at = ?
            WHERE short_name = ?
        """, (yahoo_symbol, exchange, quote_currency, now_iso(), short_name))


def bulk_set_quotes(quotes: list[dict]) -> int:
    """quotes = [{"short_name", "price", "change", "change_percent", "currency"}]"""
    if not quotes:
        return 0
    stamp = now_iso()
    payload = [
        (q["price"], q.get("change"), q.get("change_percent"),
         q.get("currency"), stamp, q["short_name"])
        for q in quotes
    ]
    with get_connection() as conn:
        cur = conn.executemany("""
            UPDATE stocks
            SET price = ?, price_change = ?, price_change_percent = ?,
                quote_currency = COALESCE(?, quote_currency), price_updated_at = ?
            WHERE short_name = ?
        """, payload)
        return cur.rowcount

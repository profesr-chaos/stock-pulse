"""News storage.

Uniqueness is enforced by the (short_name, url_hash) index rather than by a
fuzzy title scan at insert time. The previous version compared every incoming
title against every title from the last 7 days *across all stocks* at 75%
similarity, so "Stock Market Today: Nasdaq Rises" for one ticker permanently
blocked the near-identical headline for every other ticker. Story-level
deduplication now happens per stock in services/dedup.py before we get here.
"""
from __future__ import annotations

from normalize import days_ago_iso

from .connection import get_connection, one, rows

_ALLOWED_UPDATE_FIELDS = frozenset({"sentiment", "ai_summary", "image", "description", "url", "source", "source_domain"})


# ── Write ────────────────────────────────────────────────────────────────

def insert_news_many(articles: list[dict]) -> list[int]:
    """Insert prepared articles, skipping ones already stored for that stock.

    Each article must carry: short_name, title, title_key, url, url_hash,
    source, source_domain, source_type, publish_time. Returns the new row ids.
    """
    if not articles:
        return []

    inserted: list[int] = []
    with get_connection() as conn:
        for a in articles:
            cur = conn.execute("""
                INSERT OR IGNORE INTO news (
                    short_name, source, source_url, source_domain, source_country,
                    source_type, lang, publish_time, url, url_hash, image,
                    title, title_key, description, sentiment, relevance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                a["short_name"], a["source"], a.get("source_url"), a.get("source_domain"),
                a.get("source_country"), a["source_type"], a.get("lang", "en"),
                a["publish_time"], a["url"], a["url_hash"], a.get("image"),
                a["title"], a.get("title_key", ""), a.get("description"),
                a.get("sentiment"), a.get("relevance", "direct"),
            ))
            if cur.rowcount:
                inserted.append(cur.lastrowid)
    return inserted


def set_sentiment_many(scores: dict[int, float]) -> int:
    if not scores:
        return 0
    with get_connection() as conn:
        cur = conn.executemany(
            "UPDATE news SET sentiment = ? WHERE id = ?",
            [(score, news_id) for news_id, score in scores.items()],
        )
        return cur.rowcount


def update_news(news_id: int, **fields) -> bool:
    fields = {k: v for k, v in fields.items() if k in _ALLOWED_UPDATE_FIELDS}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE news SET {set_clause} WHERE id = ?", [*fields.values(), news_id]
        )
        return cur.rowcount > 0


def set_images(images: dict[int, str]) -> int:
    if not images:
        return 0
    with get_connection() as conn:
        cur = conn.executemany(
            "UPDATE news SET image = ? WHERE id = ? AND image IS NULL",
            [(url, news_id) for news_id, url in images.items()],
        )
        return cur.rowcount


def delete_older_than(cutoff_iso: str) -> int:
    with get_connection() as conn:
        return conn.execute("DELETE FROM news WHERE publish_time < ?", (cutoff_iso,)).rowcount


# ── Read ─────────────────────────────────────────────────────────────────

def get_news_by_id(news_id: int) -> dict | None:
    with get_connection() as conn:
        return one(conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)))


# Every ordering ends with `publish_time DESC, id DESC`.
#
# That tail is what makes offset paging safe: without a total order SQLite may
# return ties in any order between two queries, so page 2 could repeat or skip
# rows page 1 already showed. Sorting by sentiment alone puts thousands of
# articles on identical scores — exactly the case where that breaks.
_SORTS = {
    "recent":    "publish_time DESC, id DESC",
    "sentiment": "sentiment IS NULL, sentiment DESC, publish_time DESC, id DESC",
    "symbol":    "short_name ASC, publish_time DESC, id DESC",
    # "most news articles" is a property of the stock, not the article, so it
    # ranks by how much coverage the article's ticker has in this same window.
    "coverage":  "coverage DESC, short_name ASC, publish_time DESC, id DESC",
}
DEFAULT_SORT = "recent"


def get_news(
    short_names: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    sentiment: str | None = None,
    relevance: str | None = None,
    query: str | None = None,
    sort: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Feed query. `sentiment` is one of positive/negative/neutral.

    `short_names=None` means "every stock"; an *empty list* means "no stocks"
    and returns nothing. Treating the two the same would turn a request for an
    empty watchlist into a dump of the entire table.

    `query` is a free-text match over title, description and ticker. `sort` is
    one of _SORTS. Both are applied in SQL, not to an already-fetched page, so
    they search and order the whole table rather than the current screen.

    `offset` paginates the infinite-scroll river.
    """
    if short_names is not None and not short_names:
        return []

    where, params = ["1=1"], []

    if short_names:
        where.append(f"short_name IN ({','.join('?' * len(short_names))})")
        params += short_names
    if relevance:
        where.append("relevance = ?")
        params.append(relevance)
    if since:
        where.append("publish_time >= ?")
        params.append(since)
    if until:
        where.append("publish_time <= ?")
        params.append(until)
    if sentiment == "positive":
        where.append("sentiment > 0.2")
    elif sentiment == "negative":
        where.append("sentiment < -0.2")
    elif sentiment == "neutral":
        where.append("(sentiment IS NULL OR sentiment BETWEEN -0.2 AND 0.2)")

    term = (query or "").strip()
    if term:
        # LIKE with escaped wildcards: a user searching "100%" must not get
        # every article back. ESCAPE makes \% and \_ literal.
        pattern = "%" + term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"
        where.append(
            "(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
            "OR short_name LIKE ? ESCAPE '\\')"
        )
        params += [pattern, pattern, pattern]

    order = _SORTS.get(sort or DEFAULT_SORT, _SORTS[DEFAULT_SORT])
    filter_sql = " AND ".join(where)

    # `coverage` needs a per-ticker count over the *filtered* set, so the window
    # is computed after the WHERE rather than over the whole table.
    select = "SELECT *"
    if order.startswith("coverage"):
        select = "SELECT *, COUNT(*) OVER (PARTITION BY short_name) AS coverage"

    with get_connection() as conn:
        return rows(conn.execute(
            f"{select} FROM news WHERE {filter_sql} "
            f"ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ))


def get_trending(
    short_names: list[str] | None = None,
    since: str | None = None,
    per_stock: int = 3,
    limit: int = 12,
) -> list[dict]:
    """Articles ranked by how far their stock has moved, biggest movers first.

    `per_stock` caps how many articles one ticker contributes, or a single
    stock with heavy coverage would fill the whole section on its own. Stocks
    with no quote yet are excluded — they have no move to rank by.
    """
    if short_names is not None and not short_names:
        return []

    where, params = ["s.price_change_percent IS NOT NULL"], []
    if short_names:
        where.append(f"n.short_name IN ({','.join('?' * len(short_names))})")
        params += short_names
    if since:
        where.append("n.publish_time >= ?")
        params.append(since)

    with get_connection() as conn:
        return rows(conn.execute(f"""
            WITH ranked AS (
                SELECT n.*,
                       s.price_change_percent AS move_percent,
                       ROW_NUMBER() OVER (
                           PARTITION BY n.short_name
                           ORDER BY n.publish_time DESC, n.id DESC
                       ) AS rn
                FROM news n
                JOIN stocks s ON s.short_name = n.short_name
                WHERE {' AND '.join(where)}
            )
            SELECT * FROM ranked
            WHERE rn <= ?
            ORDER BY ABS(move_percent) DESC, publish_time DESC, id DESC
            LIMIT ?
        """, [*params, per_stock, limit]))


def get_recent_fingerprints(short_name: str, days: int = 7) -> list[dict]:
    """url_hash / title / title_key of what we already hold for this stock, so
    incoming articles can be deduped against storage as well as each other."""
    with get_connection() as conn:
        return rows(conn.execute("""
            SELECT id, url_hash, title, title_key, publish_time, source_domain,
                   (description IS NOT NULL) AS has_description,
                   (image IS NOT NULL) AS has_image
            FROM news
            WHERE short_name = ? AND publish_time >= ?
        """, (short_name, days_ago_iso(days))))


def get_unscored(limit: int = 500) -> list[dict]:
    with get_connection() as conn:
        return rows(conn.execute("""
            SELECT id, title, description FROM news
            WHERE sentiment IS NULL
            ORDER BY publish_time DESC LIMIT ?
        """, (limit,)))


def get_missing_images(short_names: list[str], limit: int = 12) -> list[dict]:
    """Newest image-less articles worth an og:image lookup. Google redirect
    links are excluded: resolving those costs a request and rarely yields one."""
    if not short_names:
        return []
    marks = ",".join("?" * len(short_names))
    with get_connection() as conn:
        return rows(conn.execute(f"""
            SELECT id, url FROM news
            WHERE short_name IN ({marks})
              AND image IS NULL
              AND source_domain NOT IN ('news.google.com', '')
              AND source_domain IS NOT NULL
            ORDER BY publish_time DESC LIMIT ?
        """, [*short_names, limit]))


def count_by_stock(since: str, short_names: list[str] | None = None) -> list[dict]:
    where, params = ["publish_time >= ?"], [since]
    if short_names:
        where.append(f"short_name IN ({','.join('?' * len(short_names))})")
        params += short_names
    with get_connection() as conn:
        return rows(conn.execute(f"""
            SELECT short_name,
                   COUNT(*)        AS article_count,
                   AVG(sentiment)  AS avg_sentiment
            FROM news
            WHERE {' AND '.join(where)}
            GROUP BY short_name
            ORDER BY article_count DESC
        """, params))


def source_breakdown(short_names: list[str], since: str) -> list[dict]:
    if not short_names:
        return []
    marks = ",".join("?" * len(short_names))
    with get_connection() as conn:
        return rows(conn.execute(f"""
            SELECT COALESCE(source_domain, source) AS source, COUNT(*) AS article_count
            FROM news
            WHERE short_name IN ({marks}) AND publish_time >= ?
            GROUP BY 1 ORDER BY article_count DESC
        """, [*short_names, since]))

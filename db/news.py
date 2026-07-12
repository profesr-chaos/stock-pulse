from .connection import get_connection
from typing import Optional
from rapidfuzz import fuzz


# ------------ INSERT --------------
def insert_news(
    short_name: str,
    source: str,
    source_type: str,
    publish_time: str,
    url: str,
    title: str,
    source_url: str = None,
    source_country: str = None,
    lang: str = None,
    image: str = None,
    description: str = None,
    sentiment: float = None,
    ai_summary: str = None,
) -> int | None:
    """Insert a news item. Returns the new row's id, or None if title already exists."""
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM news WHERE title = ?", (title,)).fetchone()

        if existing:
            #print(f"[insert_news] Exact duplicate detected, skipping: {title}")
            return None
        
        # fuzzy duplicate check
        if is_duplicate_news(title):
            #print(f"[insert_news] Fuzzy duplicate detected, skipping: {title}")
            return None

        cursor = conn.execute("""
            INSERT INTO news (
                short_name, source, source_url, source_country, source_type,
                lang, publish_time, url, image, title, description, sentiment, ai_summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (short_name, source, source_url, source_country, source_type,
              lang, publish_time, url, image, title, description, sentiment, ai_summary))
        conn.commit()
        return cursor.lastrowid


# ----------- GET --------------
def get_all_news(limit: int = 100) -> list[dict]:
    """Fetch all news, most recent first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM news ORDER BY publish_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_news_by_short_name(short_name: str, limit: int = 50, since: str = None) -> list[dict]:
    with get_connection() as conn:
        if since:
            rows = conn.execute("""
                SELECT * FROM news 
                WHERE short_name = ? AND publish_time > ?
                ORDER BY publish_time DESC LIMIT ?
            """, (short_name, since, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM news 
                WHERE short_name = ? 
                ORDER BY publish_time DESC LIMIT ?
            """, (short_name, limit)).fetchall()

        return [dict(row) for row in rows]


def get_news_by_title(title: str) -> Optional[dict]:
    """Fetch a single news item by exact title."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM news WHERE title = ?", (title,)
        ).fetchone()
        return dict(row) if row else None
    

def get_title_and_descriptions_from_ids(ids:list[int]) -> Optional[list[dict]]:
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, title, description FROM news WHERE id IN ({placeholders})",
            ids
        ).fetchall()
        return [dict(row) for row in rows]


def get_news_by_recency(limit: int = 10) -> list[dict]:
    """Fetch the most recently published news items."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM news ORDER BY publish_time DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_news_by_source_type(source_type: str, limit: int = 50) -> list[dict]:
    """Fetch news filtered by source type e.g. 'api' or 'rss'."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM news WHERE source_type = ? ORDER BY publish_time DESC LIMIT ?",
            (source_type, limit)
        ).fetchall()
        return [dict(row) for row in rows]


def get_news_by_sentiment(ascending: bool = False, limit: int = 50) -> list[dict]:
    """
    Fetch news ordered by sentiment score.
    ascending=False → most positive first (default)
    ascending=True  → most negative first
    """
    order = "ASC" if ascending else "DESC"
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM news WHERE sentiment IS NOT NULL ORDER BY sentiment {order} LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    

def get_news_by_id(id: int) -> Optional[dict]:
    """Fetch a single news item by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM news WHERE id = ?", (id,)
        ).fetchone()
        return dict(row) if row else None

    
# ----------- QUERY --------------
def is_duplicate_news(title: str, threshold: int = 75) -> bool:
    """
    Check if a similar article already exists in the db.
    Returns True if a title with similarity above threshold is found.
    """
    with get_connection() as conn:
        # only check recent articles to keep it fast
        rows = conn.execute("""
            SELECT title FROM news 
            WHERE created_at >= datetime('now', '-7 days')
        """).fetchall()

        for row in rows:
            similarity = fuzz.ratio(title.lower(), row["title"].lower())
            if similarity >= threshold:
                return True

    return False


# ----------- UPDATE --------------
def update_news_by_id(news_id: int, **fields) -> bool:
    """
    Update any fields on a news item by id.

    Usage:
        update_news_by_id(1, sentiment=0.8, ai_summary="...")
    """
    if not fields:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [news_id]

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE news SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def update_news_by_title(title: str, **fields) -> bool:
    """
    Update any fields on a news item by title.

    Usage:
        update_news_by_title("Bitcoin hits 100k", sentiment=0.9, ai_summary="...")
    """
    if not fields:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [title]

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE news SET {set_clause} WHERE title = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0
    

def bulk_update_sentiment_by_id(article_scores: dict) -> int:
    """
    Bulk update the sentiment of news articles by id.
    Returns the number of rows updated.
    """
    updates = [(score, id) for id, score in article_scores.items()]
    
    with get_connection() as conn:
        cursor = conn.executemany(
            "UPDATE news SET sentiment = ? WHERE id = ?",
            updates
        )
        conn.commit()
        return cursor.rowcount


def update_ai_summary_by_short_name(short_name: str, ai_summary: str) -> int:
    """
    Bulk update AI summary for all news items belonging to a symbol.
    Returns the number of rows updated.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE news SET ai_summary = ? WHERE short_name = ?", (ai_summary, short_name)
        )
        conn.commit()
        return cursor.rowcount



# ----------- DELETE --------------
def delete_news_older_than(cutoff_date: str) -> int:
    """
    Delete all news items published before the cutoff date.
    Returns the number of rows deleted.

    Usage:
        delete_news_older_than("2024-01-01T00:00:00Z")
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM news WHERE publish_time < ?", (cutoff_date,)
        )
        conn.commit()
        return cursor.rowcount
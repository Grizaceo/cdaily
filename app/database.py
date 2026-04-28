""" database.py — SQLite connection and queries. CDaily ONLY reads from blogwatcher tables. Own state in cdaily_starred and cdaily_summaries. """

import re
import sqlite3
from datetime import datetime
from typing import Optional

from .config import DB_PATH


def init_db() -> None:
    """Initialize CDaily's own tables in the database."""
    conn = get_connection()
    # Table for starred articles
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cdaily_starred (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id),
            starred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(article_id)
        )
        """
    )
    # Table for AI generated summaries cached per article
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cdaily_summaries (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id) UNIQUE,
            ai_summary TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Table for extracted article OpenGraph images
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cdaily_article_images (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id) UNIQUE,
            image_url TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def get_connection() -> sqlite3.Connection:
    """Returns a connection with row factory = sqlite3.Row."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_articles(
    category: str | None = None,
    query: str | None = None,
    unread_only: bool = False,
    starred: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """
    Returns list of article dicts with blog name, category, emoji merged.
    Joins articles + blogs + cdaily_starred.
    """
    conn = get_connection()
    cur = conn.cursor()

    sql = """
        SELECT
            a.id,
            a.title,
            a.url,
            a.categories,
            a.published_date,
            a.is_read,
            b.name  AS blog_name,
            s.id    AS starred_id,
            img.image_url AS og_image,
            SUMM.ai_summary AS cached_summary
        FROM articles a
        JOIN blogs    b ON a.blog_id = b.id
        LEFT JOIN cdaily_starred s ON s.article_id = a.id
        LEFT JOIN cdaily_article_images img ON img.article_id = a.id
        LEFT JOIN cdaily_summaries SUMM ON SUMM.article_id = a.id
        WHERE 1=1
    """
    params: list = []

    if unread_only:
        sql += " AND a.is_read = 0"

    if starred:
        sql += " AND s.id IS NOT NULL"

    if query:
        sql += " AND (a.title LIKE ? OR a.categories LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    # Category filter via blog name -> category mapping
    if category:
        # Build IN clause for blog names in this category
        blog_names = [k for k, v in get_blog_category_map().items() if v == category]
        if blog_names:
            placeholders = ",".join("?" * len(blog_names))
            sql += f" AND b.name IN ({placeholders})"
            params.extend(blog_names)
        else:
            return []  # No blogs in this category

    sql += " ORDER BY a.published_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    articles = []
    for row in rows:
        cat = get_blog_category(row["blog_name"])
        # use og image if present, otherwise none (frontend shows fallback)
        image_url = row["og_image"] or None
        articles.append({
            "id":            row["id"],
            "title":         row["title"] or row["url"],
            "url":           row["url"],
            "summary":       row["categories"] or "",
            "published_date": row["published_date"],
            "is_read":       bool(row["is_read"]),
            "is_starred":    row["starred_id"] is not None,
            "blog_name":     row["blog_name"],
            "category":      cat,
            "emoji":         get_emoji(cat),
            "image_url":     image_url,
        })
    return articles


def mark_read(article_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()


def mark_unread(article_id: int) -> None:
    conn = get_connection()
    conn.execute("UPDATE articles SET is_read = 0 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()


def toggle_star(article_id: int) -> bool:
    """Toggle star. Returns new state (True = starred)."""
    conn = get_connection()
    cur = conn.execute(
        "SELECT id FROM cdaily_starred WHERE article_id = ?", (article_id,)
    )
    existing = cur.fetchone()
    if existing:
        conn.execute("DELETE FROM cdaily_starred WHERE article_id = ?", (article_id,))
        conn.commit()
        conn.close()
        return False
    else:
        conn.execute(
            "INSERT OR IGNORE INTO cdaily_starred (article_id) VALUES (?)",
            (article_id,),
        )
        conn.commit()
        conn.close()
        return True


def mark_all_read() -> int:
    conn = get_connection()
    cur = conn.execute("UPDATE articles SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected


def get_article_url_and_summary(article_id: int) -> tuple[str, str | None]:
    """Returns (url, ai_summary) for an article."""
    conn = get_connection()
    cur = conn.execute(
        """
        SELECT a.url, s.ai_summary
        FROM articles a
        LEFT JOIN cdaily_summaries s ON s.article_id = a.id
        WHERE a.id = ?
        """,
        (article_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return ("", None)
    return (row["url"] or "", row["ai_summary"])


def save_ai_summary(article_id: int, summary: str) -> None:
    """Saves the AI-generated summary."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO cdaily_summaries (article_id, ai_summary) VALUES (?, ?)",
        (article_id, summary)
    )
    conn.commit()
    conn.close()


def get_article_og_image(article_id: int) -> str | None:
    """Returns cached og:image URL, or None if not fetched yet."""
    conn = get_connection()
    cur = conn.execute(
        "SELECT image_url FROM cdaily_article_images WHERE article_id = ?", (article_id,)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return row["image_url"] or None
    return None


def save_article_og_image(article_id: int, image_url: str | None) -> None:
    """Saves or clears the og:image URL for an article."""
    conn = get_connection()
    if image_url:
        conn.execute(
            "INSERT OR REPLACE INTO cdaily_article_images (article_id, image_url) VALUES (?, ?)",
            (article_id, image_url)
        )
    else:
        conn.execute(
            "DELETE FROM cdaily_article_images WHERE article_id = ?", (article_id,)
        )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    """Return unread counts total and per category."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0")
    total = cur.fetchone()[0]

    # Optimized per-category counts (single query)
    cur.execute(
        """
        SELECT b.name, COUNT(*) 
        FROM articles a
        JOIN blogs b ON a.blog_id = b.id
        WHERE a.is_read = 0
        GROUP BY b.name
        """
    )
    rows = cur.fetchall()
    
    cat_counts = {}
    blog_map = get_blog_category_map()
    for row in rows:
        blog_name = row[0]
        count = row[1]
        cat = blog_map.get(blog_name, "default")
        cat_counts[cat] = cat_counts.get(cat, 0) + count

    conn.close()
    return {"total": total, "by_category": cat_counts}


# ── Helpers ──────────────────────────────────────────────────────────────────

_category_map: dict[str, str] = {}


def get_blog_category_map() -> dict[str, str]:
    """Lazy-load the blog→category mapping from config."""
    if not _category_map:
        from .config import BLOG_CATEGORIES
        _category_map.update(BLOG_CATEGORIES)
    return _category_map


def get_blog_category(blog_name: str) -> str:
    return get_blog_category_map().get(blog_name, "default")


def get_emoji(category: str) -> str:
    from .config import CATEGORY_EMOJI
    return CATEGORY_EMOJI.get(category, CATEGORY_EMOJI.get("default", "📰"))


def _truncate(text: str | None, length: int) -> str:
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0] + "…"

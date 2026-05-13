"""Statistics queries for CDaily."""

from __future__ import annotations

from .bootstrap import get_connection
from .personalization import get_blog_category_map


def get_stats() -> dict:
    """Return unread counts total and per category."""
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0")
        total = cur.fetchone()[0]

        cur.execute("""
            SELECT b.name, COUNT(*)
            FROM articles a
            JOIN blogs b ON a.blog_id = b.id
            WHERE a.is_read = 0
            GROUP BY b.name
            """)
        rows = cur.fetchall()

    cat_counts = {}
    blog_map = get_blog_category_map()
    for row in rows:
        blog_name = row[0]
        count = row[1]
        cat = blog_map.get(blog_name, "news")
        cat_counts[cat] = cat_counts.get(cat, 0) + count

    return {"total": total, "by_category": cat_counts}

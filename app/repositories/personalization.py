"""Personalization and lookup helpers for CDaily."""

from __future__ import annotations

from contextlib import closing

from ..config import CATEGORY_EMOJI, BLOG_CATEGORIES
from .bootstrap import get_connection

_category_map: dict[str, str] = {}


def get_blog_category_map() -> dict[str, str]:
    """Lazy-load the blog→category mapping from config."""
    if not _category_map:
        _category_map.update(BLOG_CATEGORIES)
    return _category_map


def get_blog_category(blog_name: str) -> str:
    return get_blog_category_map().get(blog_name, "default")


def get_emoji(category: str) -> str:
    return CATEGORY_EMOJI.get(category, CATEGORY_EMOJI.get("default", "📰"))


def get_personalization_profile() -> dict:
    """
    Returns rating averages by blog and by category.
    Used to reorder ALL feed with lightweight personalization.
    """
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT b.name AS blog_name, AVG(r.rating) AS avg_rating
            FROM cdaily_article_ratings r
            JOIN articles a ON a.id = r.article_id
            JOIN blogs b ON b.id = a.blog_id
            GROUP BY b.name
            """)
        by_blog_rows = cur.fetchall()

    blog_category_map = get_blog_category_map()
    by_blog = {row["blog_name"]: float(row["avg_rating"]) for row in by_blog_rows}
    by_category_acc: dict[str, list[float]] = {}

    for row in by_blog_rows:
        blog_name = row["blog_name"]
        cat = blog_category_map.get(blog_name, "default")
        by_category_acc.setdefault(cat, []).append(float(row["avg_rating"]))

    by_category = {cat: (sum(values) / len(values)) for cat, values in by_category_acc.items() if values}
    return {"by_blog": by_blog, "by_category": by_category}

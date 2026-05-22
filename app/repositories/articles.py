"""Article data access helpers for CDaily."""

from __future__ import annotations

import json
from contextlib import closing

from .bootstrap import get_connection
from .personalization import get_blog_category, get_blog_category_map, get_emoji, get_personalization_profile


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
    with closing(get_connection()) as conn:
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
                SUMM.ai_summary AS cached_summary,
                r.rating AS user_rating
            FROM articles a
            JOIN blogs    b ON a.blog_id = b.id
            LEFT JOIN cdaily_starred s ON s.article_id = a.id
            LEFT JOIN cdaily_article_images img ON img.article_id = a.id
            LEFT JOIN cdaily_summaries SUMM ON SUMM.article_id = a.id
            LEFT JOIN cdaily_article_ratings r ON r.article_id = a.id
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

        if category:
            blog_names = [k for k, v in get_blog_category_map().items() if v == category]
            if blog_names:
                placeholders = ",".join("?" * len(blog_names))
                sql += f" AND b.name IN ({placeholders})"
                params.extend(blog_names)
            else:
                return []

        use_personalized_sort = category is None and not query and not starred
        fetch_limit = max(limit * 3, 200) if use_personalized_sort else limit

        sql += " ORDER BY a.published_date DESC LIMIT ? OFFSET ?"
        params.extend([fetch_limit, offset])

        cur.execute(sql, params)
        rows = cur.fetchall()

    articles = []
    for row in rows:
        cat = get_blog_category(row["blog_name"])
        image_url = row["og_image"] or None
        rating = row["user_rating"]
        raw_categories = row["categories"] or ""
        article_categories: list[str] = []
        if raw_categories:
            try:
                parsed = json.loads(raw_categories)
                if isinstance(parsed, list):
                    article_categories = [str(item).strip() for item in parsed if str(item).strip()]
                elif isinstance(parsed, str) and parsed.strip():
                    article_categories = [parsed.strip()]
            except json.JSONDecodeError:
                article_categories = [part.strip() for part in raw_categories.split(",") if part.strip()]

        articles.append(
            {
                "id": row["id"],
                "title": row["title"] or row["url"],
                "url": row["url"],
                "summary": ", ".join(article_categories[:3]),
                "categories": article_categories,
                "published_date": row["published_date"],
                "is_read": bool(row["is_read"]),
                "is_starred": row["starred_id"] is not None,
                "blog_name": row["blog_name"],
                "category": cat,
                "emoji": get_emoji(cat),
                "image_url": image_url,
                "user_rating": int(rating) if rating is not None else None,
            }
        )

    if use_personalized_sort:
        profile = get_personalization_profile()
        for article in articles:
            blog_avg = profile["by_blog"].get(article["blog_name"])
            cat_avg = profile["by_category"].get(article["category"])
            rating = article["user_rating"]

            personalized_score = 0.0
            if rating is not None:
                personalized_score += float(rating) * 2.0
            if blog_avg is not None:
                personalized_score += float(blog_avg) * 1.2
            if cat_avg is not None:
                personalized_score += float(cat_avg) * 0.8

            article["personalized_score"] = round(personalized_score, 3)

        articles.sort(
            key=lambda a: (
                a.get("personalized_score", 0.0),
                a.get("published_date") or "",
            ),
            reverse=True,
        )

    return articles[:limit]


def mark_read(article_id: int) -> None:
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))


def mark_unread(article_id: int) -> None:
    with closing(get_connection()) as conn:
        with conn:
            conn.execute("UPDATE articles SET is_read = 0 WHERE id = ?", (article_id,))


def toggle_star(article_id: int) -> bool:
    """Toggle star. Returns new state (True = starred)."""
    with closing(get_connection()) as conn:
        cur = conn.execute("SELECT id FROM cdaily_starred WHERE article_id = ?", (article_id,))
        existing = cur.fetchone()
        with conn:
            if existing:
                conn.execute("DELETE FROM cdaily_starred WHERE article_id = ?", (article_id,))
                return False
            conn.execute(
                "INSERT OR IGNORE INTO cdaily_starred (article_id) VALUES (?)",
                (article_id,),
            )
            return True


def mark_all_read() -> int:
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("UPDATE articles SET is_read = 1 WHERE is_read = 0")
            return cur.rowcount


def set_article_rating(article_id: int, rating: int | None) -> int | None:
    """
    Sets rating (1-5) for an article. If rating is None, clears existing rating.
    Returns the new rating or None when cleared.
    """
    with closing(get_connection()) as conn:
        with conn:
            if rating is None:
                conn.execute("DELETE FROM cdaily_article_ratings WHERE article_id = ?", (article_id,))
                return None

            conn.execute(
                """
                INSERT INTO cdaily_article_ratings (article_id, rating)
                VALUES (?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    rating = excluded.rating,
                    rated_at = CURRENT_TIMESTAMP
                """,
                (article_id, rating),
            )
    return rating


def get_article_url_and_summary(article_id: int) -> tuple[str, str | None]:
    """Returns (url, ai_summary) for an article."""
    with closing(get_connection()) as conn:
        cur = conn.execute(
            """
            SELECT a.url, s.ai_summary
            FROM articles a
            LEFT JOIN cdaily_summaries s ON s.article_id = a.id
            WHERE a.id = ?
            """,
            (article_id,),
        )
        row = cur.fetchone()
    if not row:
        return ("", None)
    return (row["url"] or "", row["ai_summary"])


def save_ai_summary(article_id: int, summary: str) -> None:
    """Saves the AI-generated summary."""
    with closing(get_connection()) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO cdaily_summaries (article_id, ai_summary)
                VALUES (?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    ai_summary = excluded.ai_summary,
                    created_at = CURRENT_TIMESTAMP
                """,
                (article_id, summary),
            )


def get_article_og_image(article_id: int) -> tuple[bool, str | None]:
    """Return (exists, og:image URL) from cache if any."""
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "SELECT image_url FROM cdaily_article_images WHERE article_id = ?",
            (article_id,),
        )
        row = cur.fetchone()
    if row:
        return True, row["image_url"]
    return False, None


def save_article_og_image(article_id: int, image_url: str | None) -> None:
    """Saves or clears the og:image URL for an article."""
    with closing(get_connection()) as conn:
        with conn:
            if image_url:
                conn.execute(
                    "INSERT OR REPLACE INTO cdaily_article_images (article_id, image_url) VALUES (?, ?)",
                    (article_id, image_url),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO cdaily_article_images (article_id, image_url) VALUES (?, ?)",
                    (article_id, None),
                )


def get_articles_missing_images(limit: int = 50) -> list[dict]:
    """Returns articles that don't have a record in cdaily_article_images."""
    with closing(get_connection()) as conn:
        cur = conn.execute(
            """
            SELECT a.id, a.url
            FROM articles a
            LEFT JOIN cdaily_article_images img ON img.article_id = a.id
            WHERE img.article_id IS NULL
            ORDER BY a.published_date DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [{"id": r["id"], "url": r["url"]} for r in rows]

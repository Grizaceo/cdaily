"""database.py — SQLite connection and queries. CDaily ONLY reads from blogwatcher tables."""

import sqlite3
from contextlib import closing

from .config import DB_PATH


def validate_db_schema() -> None:
    """Validate that the blogwatcher DB has required tables and columns."""
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        # Check articles table
        cur.execute("PRAGMA table_info(articles)")
        articles_cols = {row["name"] for row in cur.fetchall()}
        required_articles = {"id", "title", "url", "published_date", "is_read", "blog_id"}
        if not required_articles.issubset(articles_cols):
            missing = required_articles - articles_cols
            raise ValueError(f"Articles table missing columns: {missing}")

        # Check blogs table
        cur.execute("PRAGMA table_info(blogs)")
        blogs_cols = {row["name"] for row in cur.fetchall()}
        required_blogs = {"id", "name"}
        if not required_blogs.issubset(blogs_cols):
            missing = required_blogs - blogs_cols
            raise ValueError(f"Blogs table missing columns: {missing}")


def init_db() -> None:
    """Initialize CDaily's own tables in the database."""
    validate_db_schema()

    with closing(get_connection()) as conn:
        with conn:
            # Table for starred articles
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_starred (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id),
                    starred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(article_id)
                )
                """)
            # Table for AI generated summaries cached per article
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_summaries (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id) UNIQUE,
                    ai_summary TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)
            # Table for extracted article OpenGraph images
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_article_images (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id) UNIQUE,
                    image_url TEXT,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)
            # Table for per-article user ratings (1-5)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_article_ratings (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id) UNIQUE,
                    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                    rated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)


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

        # For ALL feed, we fetch a bigger pool and then apply personalization ranking in Python.
        use_personalized_sort = category is None and not query and not starred
        fetch_limit = max(limit * 3, 200) if use_personalized_sort else limit

        sql += " ORDER BY a.published_date DESC LIMIT ? OFFSET ?"
        params.extend([fetch_limit, offset])

        cur.execute(sql, params)
        rows = cur.fetchall()

    articles = []
    for row in rows:
        cat = get_blog_category(row["blog_name"])
        # use og image if present, otherwise none (frontend shows fallback)
        image_url = row["og_image"] or None
        rating = row["user_rating"]
        articles.append(
            {
                "id": row["id"],
                "title": row["title"] or row["url"],
                "url": row["url"],
                "summary": row["categories"] or "",
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

            # Prior preference by direct rating > blog affinity > category affinity.
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
            else:
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
                "INSERT OR REPLACE INTO cdaily_summaries (article_id, ai_summary) VALUES (?, ?)", (article_id, summary)
            )


def get_article_og_image(article_id: int) -> str | None:
    """Returns cached og:image URL, or None if not fetched yet."""
    with closing(get_connection()) as conn:
        cur = conn.execute("SELECT image_url FROM cdaily_article_images WHERE article_id = ?", (article_id,))
        row = cur.fetchone()
    if row:
        return row["image_url"] or None
    return None


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
                    "INSERT OR IGNORE INTO cdaily_article_images (article_id, image_url) VALUES (?, ?)", (article_id, None)
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


def get_stats() -> dict:
    """Return unread counts total and per category."""
    with closing(get_connection()) as conn:
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

    return {"total": total, "by_category": cat_counts}


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

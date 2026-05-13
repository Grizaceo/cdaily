"""Bootstrap and schema validation for the shared SQLite database."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from ..config import DB_PATH


def validate_db_schema() -> None:
    """Validate that the blogwatcher DB has required tables and columns."""
    with closing(get_connection()) as conn:
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(articles)")
        articles_cols = {row["name"] for row in cur.fetchall()}
        required_articles = {"id", "title", "url", "published_date", "is_read", "blog_id"}
        if not required_articles.issubset(articles_cols):
            missing = required_articles - articles_cols
            raise ValueError(f"Articles table missing columns: {missing}")

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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_starred (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id),
                    starred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(article_id)
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_summaries (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id) UNIQUE,
                    ai_summary TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdaily_article_images (
                    id INTEGER PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id) UNIQUE,
                    image_url TEXT,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)
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

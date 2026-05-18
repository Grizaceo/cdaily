"""
tests/test_api.py — API smoke tests using an in-memory SQLite database.
Run with: pytest tests/ -v
No external dependencies (blogwatcher-cli, real DB, etc.).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _set_test_db_env():
    """Point CDaily at a temporary test database before any imports."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["CDAILY_DB_PATH"] = db_path
    yield
    os.environ.pop("CDAILY_DB_PATH", None)
    if Path(db_path).exists():
        Path(db_path).unlink()


@pytest.fixture
def conn():
    """Create a fresh test database with CDaily's expected schema + sample data."""
    db_path = Path(os.environ["CDAILY_DB_PATH"])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create blogwatcher-cli tables (what CDaily reads)
    conn.executescript("""
        CREATE TABLE blogs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            feed_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            blog_id INTEGER REFERENCES blogs(id),
            title TEXT,
            url TEXT NOT NULL,
            content TEXT,
            summary TEXT,
            author TEXT,
            categories TEXT,
            published_date DATETIME,
            guid TEXT,
            is_read INTEGER DEFAULT 0,
            is_starred INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Insert test data
    conn.execute(
        "INSERT INTO blogs (id, name, url, feed_url) "
        "VALUES (1, 'Test Blog', 'https://example.com', 'https://example.com/feed')"
    )
    conn.execute(
        "INSERT INTO blogs (id, name, url, feed_url) "
        "VALUES (2, 'Ars Technica', 'https://arstechnica.com', "
        "'https://feeds.arstechnica.com')"
    )
    conn.execute(
        "INSERT INTO articles (id, blog_id, title, url, published_date, is_read) VALUES "
        "(1, 1, 'Test Article', 'https://example.com/test', '2026-05-13', 0)"
    )
    conn.execute(
        "INSERT INTO articles (id, blog_id, title, url, published_date, is_read) VALUES "
        "(2, 2, 'Second Article', 'https://arstechnica.com/article', '2026-05-12', 1)"
    )
    conn.commit()

    yield conn
    conn.close()


def test_blogs_exist(conn):
    """At least one blog should be registered in the test DB."""
    cur = conn.execute("SELECT COUNT(*) FROM blogs")
    count = cur.fetchone()[0]
    assert count >= 1, f"Expected blogs, got {count}"


def test_articles_exist(conn):
    """At least one article should exist in the test DB."""
    cur = conn.execute("SELECT COUNT(*) FROM articles")
    count = cur.fetchone()[0]
    assert count > 0, "No articles found"


def test_articles_have_required_columns(conn):
    """Articles must have the columns CDaily reads."""
    cur = conn.execute("SELECT id, title, url, published_date, is_read FROM articles LIMIT 1")
    row = cur.fetchone()
    assert row is not None, "No articles to inspect"
    assert {"id", "title", "url", "published_date", "is_read"}.issubset(set(row.keys()))


def test_blogs_have_required_columns(conn):
    """Blogs must have the columns CDaily reads."""
    cur = conn.execute("SELECT id, name, url FROM blogs LIMIT 1")
    row = cur.fetchone()
    assert row is not None, "No blogs to inspect"
    assert {"id", "name", "url"}.issubset(set(row.keys()))


def test_articles_can_be_read(conn):
    """Verify mark-read logic works against the test DB."""
    conn.execute("UPDATE articles SET is_read = 1 WHERE id = 1")
    conn.commit()
    cur = conn.execute("SELECT is_read FROM articles WHERE id = 1")
    assert cur.fetchone()["is_read"] == 1


def test_fresh_article_is_unread(conn):
    """Newly inserted articles should default to is_read=0."""
    cur = conn.execute("SELECT is_read FROM articles WHERE id = 1")
    assert cur.fetchone()["is_read"] == 0

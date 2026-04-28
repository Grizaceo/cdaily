"""
tests/test_api.py — Basic API smoke tests.
Run with: pytest tests/ -v
"""

import sqlite3
from pathlib import Path

import pytest

# Point at the real blogwatcher DB for integration tests
DB = Path.home() / ".blogwatcher-cli" / "blogwatcher-cli.db"


@pytest.fixture
def conn():
    if not DB.exists():
        pytest.skip("blogwatcher-cli.db not found")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def test_blogs_exist(conn):
    """At least one blog should be registered."""
    cur = conn.execute("SELECT COUNT(*) FROM blogs")
    count = cur.fetchone()[0]
    assert count >= 20, f"Expected 20+ blogs, got {count}"


def test_articles_exist(conn):
    """At least one article should exist."""
    cur = conn.execute("SELECT COUNT(*) FROM articles")
    count = cur.fetchone()[0]
    assert count > 0, "No articles found"


def test_articles_have_required_columns(conn):
    """Articles must have the columns CDaily reads."""
    cur = conn.execute(
        "SELECT id, title, url, published_date, is_read FROM articles LIMIT 1"
    )
    row = cur.fetchone()
    assert row is not None, "No articles to inspect"
    assert {"id", "title", "url", "published_date", "is_read"}.issubset(set(row.keys()))


def test_blogs_have_required_columns(conn):
    """Blogs must have the columns CDaily reads."""
    cur = conn.execute("SELECT id, name, url FROM blogs LIMIT 1")
    row = cur.fetchone()
    assert row is not None, "No blogs to inspect"
    assert {"id", "name", "url"}.issubset(set(row.keys()))

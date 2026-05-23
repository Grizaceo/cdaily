"""Smoke tests for the CDaily MCP server.

Verifies the server module loads, all tools/resources/prompts register
cleanly, and the shaping helpers behave correctly. Full integration tests
would require driving the MCP runtime, which we leave to manual checks via
Claude Code / mcp-cli.
"""

from __future__ import annotations

import pytest


def test_module_imports() -> None:
    """The mcp_server module imports without errors and builds the FastMCP."""
    from cdaily import mcp_server

    assert mcp_server.mcp is not None
    assert mcp_server.mcp.name == "cdaily"


def test_tools_registered() -> None:
    """All advertised tools are reachable via the FastMCP tool manager."""
    import asyncio

    from cdaily import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "feed_read",
        "feed_digest",
        "feed_search",
        "article_open",
        "article_mark_apply",
        "article_rate_apply",
        "article_summarize_apply",
        "feed_clear_apply",
        "sources_list",
        "sources_add_apply",
        "sources_remove_apply",
        "feed_scan_apply",
        "feed_stats",
    }
    missing = expected - names
    assert not missing, f"Missing tools: {missing}"


def test_resources_registered() -> None:
    """The three resource URIs are reachable."""
    import asyncio

    from cdaily import mcp_server

    resources = asyncio.run(mcp_server.mcp.list_resources())
    uris = {str(r.uri) for r in resources}
    assert uris == {
        "cdaily://feed/unread",
        "cdaily://stats",
        "cdaily://sources",
    }


def test_prompts_registered() -> None:
    """The two workflow prompts are reachable."""
    import asyncio

    from cdaily import mcp_server

    prompts = asyncio.run(mcp_server.mcp.list_prompts())
    names = {p.name for p in prompts}
    assert names == {"morning_triage", "weekly_digest"}


def test_shaping_slim_article() -> None:
    from cdaily.mcp.shaping import slim_article

    a = {
        "id": 1,
        "title": "T",
        "url": "https://x/y",
        "blog_name": "B",
        "published_date": "2026-01-01",
        "is_starred": False,
        "user_rating": 4,
        "category": "tech",
    }
    s = slim_article(a)
    assert s["id"] == 1
    assert s["blog"] == "B"
    assert "url" not in s  # slim drops url
    assert s["rating"] == 4


def test_shaping_verbose_article_adds_url() -> None:
    from cdaily.mcp.shaping import verbose_article

    a = {
        "id": 1,
        "title": "T",
        "url": "https://x/y",
        "blog_name": "B",
        "published_date": "2026-01-01",
        "is_starred": False,
        "user_rating": None,
        "category": "tech",
        "summary": "s",
        "image_url": "img",
        "personalized_score": 3.0,
        "emoji": "📰",
        "is_read": False,
    }
    v = verbose_article(a)
    assert v["url"] == "https://x/y"
    assert v["summary"] == "s"
    assert v["image_url"] == "img"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Build a temporary blogwatcher-cli-shaped DB and point CDaily config at it."""
    import sqlite3

    db = tmp_path / "blogwatcher-cli.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE blogs (
            id INTEGER PRIMARY KEY, name TEXT, url TEXT,
            feed_url TEXT, scrape_selector TEXT, last_scanned TEXT
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, title TEXT, url TEXT,
            categories TEXT, published_date TEXT,
            is_read INTEGER DEFAULT 0, blog_id INTEGER
        );
        CREATE TABLE cdaily_starred (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE);
        CREATE TABLE cdaily_summaries (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, ai_summary TEXT);
        CREATE TABLE cdaily_article_images (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, image_url TEXT);
        CREATE TABLE cdaily_article_ratings (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, rating INTEGER);

        INSERT INTO blogs VALUES (1, 'Test Blog', 'https://test', NULL, NULL, NULL);
        INSERT INTO articles VALUES (1, 'Hello world', 'https://test/a', NULL, '2026-05-23', 0, 1);
        INSERT INTO articles VALUES (2, 'Second article', 'https://test/b', NULL, '2026-05-22', 1, 1);
        """
    )
    conn.commit()
    conn.close()

    from pathlib import Path

    from cdaily import config as cfg

    monkeypatch.setattr(cfg, "DB_PATH", Path(str(db)))
    yield db


def test_feed_read_returns_unread(isolated_db) -> None:
    """Drives the feed_read tool through the FastMCP harness end-to-end."""
    import asyncio

    from cdaily import mcp_server

    result = asyncio.run(
        mcp_server.mcp.call_tool("feed_read", {"filter": "unread", "limit": 10})
    )
    # FastMCP call_tool returns a tuple (content, structured) or list; normalise.
    payload = result[1] if isinstance(result, tuple) else result
    if isinstance(payload, dict) and "articles" in payload:
        articles = payload["articles"]
    else:
        # Older FastMCP returns list[Content] — extract structured content
        import json

        raw = payload[0].text if hasattr(payload[0], "text") else str(payload[0])
        articles = json.loads(raw).get("articles", [])
    assert any(a.get("id") == 1 for a in articles)


def test_feed_stats_returns_total(isolated_db) -> None:
    import asyncio

    from cdaily import mcp_server

    result = asyncio.run(mcp_server.mcp.call_tool("feed_stats", {}))
    payload = result[1] if isinstance(result, tuple) else result
    if isinstance(payload, dict) and "total" in payload:
        assert payload["total"] >= 1
    else:
        import json

        raw = payload[0].text if hasattr(payload[0], "text") else str(payload[0])
        stats = json.loads(raw)
        assert stats["total"] >= 1

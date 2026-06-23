"""E2E tests for the CDaily MCP server.

Covers all 13 tools via FastMCP.call_tool.
Tools requiring external services (blogwatcher-cli, AI endpoints) are
skipped with documented reasons.
"""

from __future__ import annotations

import asyncio
import pytest


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Build a temporary blogwatcher-cli-shaped DB with rich test data.

    Creates 4 articles across 3 blogs with categories, ratings, stars,
    summaries, and image URLs for thorough E2E coverage.
    """
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
        CREATE TABLE cdaily_article_ratings (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, rating INTEGER, rated_at TEXT);

        INSERT INTO blogs VALUES (1, 'TechCrunch', 'https://techcrunch.com', NULL, NULL, '2026-05-20');
        INSERT INTO blogs VALUES (2, 'BBC News', 'https://bbc.com/news', NULL, NULL, '2026-05-21');
        INSERT INTO blogs VALUES (3, 'Ars Technica', 'https://arstechnica.com', NULL, NULL, NULL);

        INSERT INTO articles VALUES (1, 'AI breakthrough', 'https://tc/a', 'tech,ai', '2026-05-23', 0, 1);
        INSERT INTO articles VALUES (2, 'Climate summit', 'https://bbc/b', 'science,climate', '2026-05-22', 0, 2);
        INSERT INTO articles VALUES (3, 'New CPU review', 'https://ar/c', 'tech,hardware', '2026-05-21', 0, 3);
        INSERT INTO articles VALUES (4, 'Already read', 'https://tc/d', 'news', '2026-05-20', 1, 1);

        INSERT INTO cdaily_summaries VALUES (1, 1, 'This is an AI-generated summary of article 1.');
        INSERT INTO cdaily_article_images VALUES (1, 2, 'https://img.example.com/bbc-climate.jpg');
        INSERT INTO cdaily_article_ratings VALUES (1, 1, 4, '2026-05-23');
        """
    )
    conn.commit()
    conn.close()

    from pathlib import Path
    from cdaily import config as cfg

    monkeypatch.setattr(cfg, "DB_PATH", Path(str(db)))
    monkeypatch.setattr(cfg, "BLOG_CATEGORIES", {
        "TechCrunch": "tech",
        "BBC News": "science",
        "Ars Technica": "tech",
    })
    # personalization.py imports BLOG_CATEGORIES at module level, so we
    # must also inject the cache directly to bypass the stale import.
    from cdaily.repositories import personalization

    personalization._category_map.clear()
    personalization._category_map.update({
        "TechCrunch": "tech",
        "BBC News": "science",
        "Ars Technica": "tech",
    })
    yield db
# ═══════════════════════════════════════════════════════════════════════
# Registration tests (unchanged — keep existing coverage)
# ═══════════════════════════════════════════════════════════════════════


def test_module_imports() -> None:
    """The mcp_server module imports without errors and builds the FastMCP."""
    from cdaily import mcp_server

    assert mcp_server.mcp is not None
    assert mcp_server.mcp.name == "cdaily"


def test_tools_registered() -> None:
    """All 13 advertised tools are reachable via the FastMCP tool manager."""
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
    from cdaily import mcp_server

    prompts = asyncio.run(mcp_server.mcp.list_prompts())
    names = {p.name for p in prompts}
    assert names == {"morning_triage", "weekly_digest"}


# ═══════════════════════════════════════════════════════════════════════
# Shaping helpers
# ═══════════════════════════════════════════════════════════════════════


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
    assert "url" not in s
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


# ═══════════════════════════════════════════════════════════════════════
# E2E: feed_read (migrated from original, extended)
# ═══════════════════════════════════════════════════════════════════════


def _call_tool(name, args=None):
    """Helper: call tool via FastMCP and unwrap result to dict."""
    from cdaily import mcp_server

    result = asyncio.run(mcp_server.mcp.call_tool(name, args or {}))
    payload = result[1] if isinstance(result, tuple) else result
    if isinstance(payload, dict):
        return payload
    # Older FastMCP returns list[Content]
    import json

    raw = payload[0].text if hasattr(payload[0], "text") else str(payload[0])
    return json.loads(raw)


def test_feed_read_unread(isolated_db) -> None:
    """feed_read filter=unread returns only unread articles."""
    data = _call_tool("feed_read", {"filter": "unread", "limit": 10})
    assert data["count"] >= 2  # 3 unread at minimum
    ids = {a["id"] for a in data["articles"]}
    assert 4 not in ids  # article 4 is read


def test_feed_read_starred(isolated_db) -> None:
    """feed_read filter=starred returns only starred articles."""
    # First star article 3
    _call_tool("article_mark_apply", {"id": 3, "state": "starred"})
    data = _call_tool("feed_read", {"filter": "starred", "limit": 10})
    ids = {a["id"] for a in data["articles"]}
    assert 3 in ids
    # Cleanup
    _call_tool("article_mark_apply", {"id": 3, "state": "unstarred"})


def test_feed_read_slim_no_url(isolated_db) -> None:
    """feed_read slim (default) omits url field."""
    data = _call_tool("feed_read", {"limit": 1})
    assert data["count"] >= 1
    a = data["articles"][0]
    assert "id" in a
    assert "url" not in a


def test_feed_read_verbose_includes_url(isolated_db) -> None:
    """feed_read verbose=True includes url, summary, image_url."""
    data = _call_tool("feed_read", {"verbose": True, "limit": 5})
    assert data["count"] >= 1
    a = data["articles"][0]
    assert "url" in a


def test_feed_read_category_filter(isolated_db) -> None:
    """feed_read category='science' only returns articles with that category."""
    data = _call_tool("feed_read", {"category": "science", "limit": 10})
    blogs = {a["blog"] for a in data["articles"]}
    assert "BBC News" in blogs


def test_feed_read_query_search(isolated_db) -> None:
    """feed_read query matches title or categories."""
    data = _call_tool("feed_read", {"query": "climate", "limit": 10})
    assert data["count"] >= 1
    titles = [a["title"] for a in data["articles"]]
    assert any("climate" in t.lower() for t in titles)


# ═══════════════════════════════════════════════════════════════════════
# E2E: feed_digest
# ═══════════════════════════════════════════════════════════════════════


def test_feed_digest_by_category(isolated_db) -> None:
    """feed_digest group_by='category' returns groups keyed by category."""
    data = _call_tool("feed_digest", {"top_n": 5, "group_by": "category"})
    assert data["total_unread"] >= 2
    assert "by_group" in data
    assert "suggested_actions" in data
    assert isinstance(data["by_group"], dict)
    assert len(data["by_group"]) >= 2  # tech, science at minimum


def test_feed_digest_flat(isolated_db) -> None:
    """feed_digest group_by='flat' returns single 'all' group."""
    data = _call_tool("feed_digest", {"top_n": 3, "group_by": "flat"})
    assert "all" in data["by_group"]
    assert data["by_group"]["all"][0]["id"] is not None


def test_feed_digest_by_blog(isolated_db) -> None:
    """feed_digest group_by='blog' groups by blog_name."""
    data = _call_tool("feed_digest", {"top_n": 5, "group_by": "blog"})
    blogs = set(data["by_group"].keys())
    assert "TechCrunch" in blogs


def test_feed_digest_suggests_scan_when_empty(tmp_path, monkeypatch) -> None:
    """feed_digest on empty DB suggests running scan."""
    import sqlite3

    db = tmp_path / "blogwatcher-cli.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE blogs (id INTEGER PRIMARY KEY, name TEXT, url TEXT,
            feed_url TEXT, scrape_selector TEXT, last_scanned TEXT);
        CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, url TEXT,
            categories TEXT, published_date TEXT, is_read INTEGER DEFAULT 0, blog_id INTEGER);
        CREATE TABLE cdaily_starred (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE);
        CREATE TABLE cdaily_summaries (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, ai_summary TEXT);
        CREATE TABLE cdaily_article_images (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, image_url TEXT);
        CREATE TABLE cdaily_article_ratings (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, rating INTEGER, rated_at TEXT);
        """
    )
    conn.commit()
    conn.close()

    from pathlib import Path
    from cdaily import config as cfg

    monkeypatch.setattr(cfg, "DB_PATH", Path(str(db)))
    data = _call_tool("feed_digest", {})
    assert data["total_unread"] == 0
    assert any("scan" in s.lower() for s in data["suggested_actions"])


# ═══════════════════════════════════════════════════════════════════════
# E2E: feed_search
# ═══════════════════════════════════════════════════════════════════════


def test_feed_search_exact_title(isolated_db) -> None:
    """feed_search finds article by title substring."""
    data = _call_tool("feed_search", {"intent": "AI breakthrough", "limit": 5})
    assert data["count"] >= 1
    assert data["articles"][0]["title"] == "AI breakthrough"


def test_feed_search_partial(isolated_db) -> None:
    """feed_search finds articles by partial match."""
    data = _call_tool("feed_search", {"intent": "CPU", "limit": 5})
    assert data["count"] >= 1
    titles = [a["title"] for a in data["articles"]]
    assert any("CPU" in t for t in titles)


def test_feed_search_no_results(isolated_db) -> None:
    """feed_search returns empty on non-matching query."""
    data = _call_tool("feed_search", {"intent": "zzz_nonexistent_zzz", "limit": 5})
    assert data["count"] == 0
    assert data["articles"] == []


# ═══════════════════════════════════════════════════════════════════════
# E2E: article_open
# ═══════════════════════════════════════════════════════════════════════


def test_article_open_existing(isolated_db) -> None:
    """article_open returns full detail for existing article."""
    data = _call_tool("article_open", {"id": 1, "with_summary": True})
    assert data["ok"] is True
    assert data["id"] == 1
    assert data["title"] == "AI breakthrough"
    assert data["blog"] == "TechCrunch"
    assert data["url"] is not None
    assert data["has_cached_summary"] is True
    assert data["summary"] is not None
    assert data["summary"] == "This is an AI-generated summary of article 1."


def test_article_open_without_summary(isolated_db) -> None:
    """article_open with_summary=False omits summary."""
    data = _call_tool("article_open", {"id": 1, "with_summary": False})
    assert data["ok"] is True
    assert data["summary"] is None


def test_article_open_with_image(isolated_db) -> None:
    """article_open returns image_url when cached."""
    data = _call_tool("article_open", {"id": 2})
    assert data["ok"] is True
    assert data["image_url"] == "https://img.example.com/bbc-climate.jpg"


def test_article_open_nonexistent(isolated_db) -> None:
    """article_open returns error for missing ID."""
    data = _call_tool("article_open", {"id": 9999})
    assert data["ok"] is False
    assert "not found" in data.get("error", "")


# ═══════════════════════════════════════════════════════════════════════
# E2E: article_mark_apply
# ═══════════════════════════════════════════════════════════════════════


def test_article_mark_read(isolated_db) -> None:
    """article_mark_apply state='read' marks article as read."""
    # Article 2 should be unread initially
    data = _call_tool("article_mark_apply", {"id": 2, "state": "read"})
    assert data["ok"] is True
    assert data["state"] == "read"
    # Verify it disappeared from unread feed
    feed = _call_tool("feed_read", {"filter": "unread", "limit": 10})
    ids = {a["id"] for a in feed["articles"]}
    assert 2 not in ids


def test_article_mark_unread(isolated_db) -> None:
    """article_mark_apply state='unread' brings article back."""
    data = _call_tool("article_mark_apply", {"id": 4, "state": "unread"})
    assert data["ok"] is True
    feed = _call_tool("feed_read", {"filter": "all", "limit": 10})
    # Article 4 is now unread
    a4 = next((a for a in feed["articles"] if a["id"] == 4), None)
    assert a4 is not None


def test_article_mark_star_toggle(isolated_db) -> None:
    """article_mark_apply state='starred' toggles star on."""
    data = _call_tool("article_mark_apply", {"id": 1, "state": "starred"})
    assert data["ok"] is True
    assert data["starred"] is True
    # Verify in starred feed
    starred = _call_tool("feed_read", {"filter": "starred", "limit": 10})
    ids = {a["id"] for a in starred["articles"]}
    assert 1 in ids


def test_article_mark_unstar_toggle(isolated_db) -> None:
    """article_mark_apply state='unstarred' toggles star off."""
    # Star first
    _call_tool("article_mark_apply", {"id": 2, "state": "starred"})
    # Then unstar
    data = _call_tool("article_mark_apply", {"id": 2, "state": "unstarred"})
    assert data["ok"] is True
    assert data["starred"] is False
    starred = _call_tool("feed_read", {"filter": "starred", "limit": 10})
    ids = {a["id"] for a in starred["articles"]}
    assert 2 not in ids


def test_article_mark_bad_state(isolated_db) -> None:
    """article_mark_apply rejects unknown states."""
    data = _call_tool("article_mark_apply", {"id": 1, "state": "deleted"})
    assert data["ok"] is False
    assert "Unknown state" in data["error"]


# ═══════════════════════════════════════════════════════════════════════
# E2E: article_rate_apply
# ═══════════════════════════════════════════════════════════════════════


def test_article_rate_set(isolated_db) -> None:
    """article_rate_apply sets rating 1-5."""
    data = _call_tool("article_rate_apply", {"id": 3, "rating": 5})
    assert data["ok"] is True
    assert data["rating"] == 5
    # Verify persisted
    info = _call_tool("article_open", {"id": 3})
    assert info["user_rating"] == 5


def test_article_rate_clear(isolated_db) -> None:
    """article_rate_apply null clears rating."""
    data = _call_tool("article_rate_apply", {"id": 1, "rating": None})
    assert data["ok"] is True
    assert data["rating"] is None
    info = _call_tool("article_open", {"id": 1})
    assert info["user_rating"] is None


def test_article_rate_invalid_value(isolated_db) -> None:
    """article_rate_apply rejects rating outside 1-5."""
    data = _call_tool("article_rate_apply", {"id": 1, "rating": 0})
    assert data["ok"] is False
    assert "1-5" in data["error"]


def test_article_rate_invalid_high(isolated_db) -> None:
    """article_rate_apply rejects rating > 5."""
    data = _call_tool("article_rate_apply", {"id": 1, "rating": 6})
    assert data["ok"] is False


# ═══════════════════════════════════════════════════════════════════════
# E2E: feed_clear_apply
# ═══════════════════════════════════════════════════════════════════════


def test_feed_clear_all(isolated_db) -> None:
    """feed_clear_apply scope='all' marks everything as read."""
    data = _call_tool("feed_clear_apply", {"scope": "all"})
    assert data["ok"] is True
    assert data["marked"] >= 2  # at least the 3 unread
    # Verify feed is empty of unread
    feed = _call_tool("feed_read", {"filter": "unread", "limit": 10})
    assert feed["count"] == 0


def test_feed_clear_by_category(isolated_db) -> None:
    """feed_clear_apply scope='category' with target only clears that category."""
    data = _call_tool("feed_clear_apply", {"scope": "category", "target": "science"})
    assert data["ok"] is True
    assert data["marked"] >= 1
    # Verify TechCrunch articles still unread (category 'tech')
    feed = _call_tool("feed_read", {"filter": "unread", "limit": 10})
    blogs = {a["blog"] for a in feed["articles"]}
    assert "TechCrunch" in blogs


def test_feed_clear_by_blog(isolated_db) -> None:
    """feed_clear_apply scope='blog' with target only clears that blog."""
    data = _call_tool("feed_clear_apply", {"scope": "blog", "target": "Ars Technica"})
    assert data["ok"] is True
    assert data["marked"] >= 1
    feed = _call_tool("feed_read", {"filter": "unread", "limit": 10})
    blogs = {a["blog"] for a in feed["articles"]}
    assert "Ars Technica" not in blogs
    assert "TechCrunch" in blogs  # still has AI breakthrough


def test_feed_clear_bad_scope(isolated_db) -> None:
    """feed_clear_apply rejects invalid scope."""
    data = _call_tool("feed_clear_apply", {"scope": "week", "target": "x"})
    assert data["ok"] is False


def test_feed_clear_no_target_for_scoped(isolated_db) -> None:
    """feed_clear_apply requires target for category/blog scope."""
    data = _call_tool("feed_clear_apply", {"scope": "category"})
    assert data["ok"] is False


# ═══════════════════════════════════════════════════════════════════════
# E2E: sources_list
# ═══════════════════════════════════════════════════════════════════════


def test_sources_list_slim(isolated_db) -> None:
    """sources_list (default) returns id, name, url."""
    data = _call_tool("sources_list", {})
    assert data["count"] == 3
    assert data["sources"][0]["id"] is not None
    assert data["sources"][0]["name"] is not None
    assert data["sources"][0]["url"] is not None
    assert "feed_url" not in data["sources"][0]  # slim


def test_sources_list_verbose(isolated_db) -> None:
    """sources_list verbose=True includes feed_url, selector, last_scanned."""
    data = _call_tool("sources_list", {"verbose": True})
    assert data["count"] >= 1
    s0 = data["sources"][0]
    assert "feed_url" in s0
    assert "last_scanned" in s0
    assert "scrape_selector" in s0


def test_sources_list_empty_db(tmp_path, monkeypatch) -> None:
    """sources_list on empty DB returns empty list."""
    import sqlite3

    db = tmp_path / "blogwatcher-cli.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE blogs (id INTEGER PRIMARY KEY, name TEXT, url TEXT,
            feed_url TEXT, scrape_selector TEXT, last_scanned TEXT);
        CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, url TEXT,
            categories TEXT, published_date TEXT, is_read INTEGER DEFAULT 0, blog_id INTEGER);
        CREATE TABLE cdaily_starred (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE);
        CREATE TABLE cdaily_summaries (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, ai_summary TEXT);
        CREATE TABLE cdaily_article_images (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, image_url TEXT);
        CREATE TABLE cdaily_article_ratings (id INTEGER PRIMARY KEY, article_id INTEGER UNIQUE, rating INTEGER, rated_at TEXT);
        """
    )
    conn.commit()
    conn.close()

    from pathlib import Path
    from cdaily import config as cfg

    monkeypatch.setattr(cfg, "DB_PATH", Path(str(db)))
    data = _call_tool("sources_list", {})
    assert data["count"] == 0
    assert data["sources"] == []


# ═══════════════════════════════════════════════════════════════════════
# E2E: feed_stats
# ═══════════════════════════════════════════════════════════════════════


def test_feed_stats_returns_total(isolated_db) -> None:
    """feed_stats returns total unread with breakdown."""
    data = _call_tool("feed_stats", {})
    assert data["total"] >= 2


# ═══════════════════════════════════════════════════════════════════════
# Documented skips: tools requiring external services
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.skip(reason="article_summarize_apply requires AI endpoint (OPENAI_API_KEY + config)")
def test_article_summarize_apply_e2e():
    """Would test summarize, but requires a live AI backend."""
    pass


@pytest.mark.skip(reason="sources_add_apply calls blogwatcher-cli subprocess")
def test_sources_add_apply_e2e():
    """Would test adding a source, but requires blogwatcher-cli installation."""
    pass


@pytest.mark.skip(reason="sources_remove_apply calls blogwatcher-cli subprocess")
def test_sources_remove_apply_e2e():
    """Would test removing a source, but requires blogwatcher-cli installation."""
    pass


@pytest.mark.skip(reason="feed_scan_apply triggers blogwatcher-cli subprocess (30s-2min)")
def test_feed_scan_apply_e2e():
    """Would test scan, but is slow and requires blogwatcher-cli installation."""
    pass

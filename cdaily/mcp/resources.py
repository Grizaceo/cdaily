"""MCP resources — passive, read-only views of CDaily state.

Agents can attach these via @cdaily://... without spending a tool call.
"""

from __future__ import annotations

import json
from contextlib import closing

from mcp.server.fastmcp import FastMCP

from ..repositories.articles import get_articles
from ..repositories.bootstrap import get_connection
from ..repositories.stats import get_stats
from .shaping import slim_article, slim_blog


def register_resources(mcp: FastMCP) -> None:
    @mcp.resource("cdaily://feed/unread")
    def feed_unread() -> str:
        """Snapshot of unread articles (top 50, slim)."""
        articles = get_articles(unread_only=True, limit=50)
        return json.dumps(
            {"count": len(articles), "articles": [slim_article(a) for a in articles]},
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("cdaily://stats")
    def stats() -> str:
        """Current unread counts snapshot."""
        return json.dumps(get_stats(), ensure_ascii=False, indent=2)

    @mcp.resource("cdaily://sources")
    def sources() -> str:
        """Tracked blog sources (slim)."""
        with closing(get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, name, url FROM blogs ORDER BY name ASC")
            rows = cur.fetchall()
        return json.dumps(
            [slim_blog(dict(r)) for r in rows], ensure_ascii=False, indent=2
        )

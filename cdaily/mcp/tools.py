"""Agent-native tools for the CDaily MCP server.

Tools follow these conventions:
- Verbs that complete user intent in one call (digest, triage), not raw API mirrors.
- Slim payloads by default; verbose=True for deep-dive.
- Mutating tools carry `[MUTATES]` in docstring + `_apply` suffix in name.
- Descriptions tell agents WHEN to use a tool, not just what it does.
"""

from __future__ import annotations

from contextlib import closing
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..config import CONFIG
from ..repositories.articles import (
    get_articles,
    mark_all_read,
    mark_read,
    mark_unread,
    set_article_rating,
    toggle_star,
)
from ..repositories.bootstrap import get_connection
from ..repositories.stats import get_stats
from ..services.article_summary import summarize_article
from ..services.blogs import add_blog as svc_add_blog
from ..services.blogs import remove_blog as svc_remove_blog
from ..services.scan import run_scan
from .shaping import slim_article, slim_blog, verbose_article, verbose_blog


def register_tools(mcp: FastMCP) -> None:
    # ─── Lectura / descubrimiento ─────────────────────────────────────────

    @mcp.tool()
    def feed_read(
        filter: str = "unread",
        category: str | None = None,
        query: str | None = None,
        limit: int = 20,
        verbose: bool = False,
    ) -> dict[str, Any]:
        """Read articles from the CDaily feed with filters.

        Use when you need a snapshot of the feed before acting.

        Args:
            filter: 'unread' (default), 'starred', or 'all'.
            category: optional category name (news, tech, finance, etc).
            query: optional search string matching title or categories.
            limit: max articles (default 20, capped at 200).
            verbose: include url, summary, image_url, scores (default false → slim).

        Returns: {count, articles[]}. Slim by default.
        """
        unread = filter == "unread"
        starred = filter == "starred"
        articles = get_articles(
            category=category,
            query=query,
            unread_only=unread,
            starred=starred,
            limit=min(limit, 200),
            offset=0,
        )
        shaper = verbose_article if verbose else slim_article
        return {"count": len(articles), "articles": [shaper(a) for a in articles]}

    @mcp.tool()
    def feed_digest(top_n: int = 5, group_by: str = "category") -> dict[str, Any]:
        """Pre-grouped briefing of the unread feed.

        Use when the user says "what's new" or "catch me up" — one round-trip
        gives a structured digest instead of N separate calls.

        Args:
            top_n: max articles per group (default 5).
            group_by: 'category', 'blog', or 'flat'.

        Returns: {total_unread, by_group, suggested_actions[]}.
        """
        articles = get_articles(unread_only=True, limit=200)
        total = len(articles)
        groups: dict[str, list[dict[str, Any]]] = {}

        if group_by == "flat":
            groups["all"] = [slim_article(a) for a in articles[:top_n]]
        else:
            key = "category" if group_by == "category" else "blog_name"
            for a in articles:
                k = a.get(key) or "uncategorized"
                groups.setdefault(k, [])
                if len(groups[k]) < top_n:
                    groups[k].append(slim_article(a))

        suggested: list[str] = []
        if total == 0:
            suggested.append("Run feed_scan_apply to refresh from sources.")
        elif total > 50:
            suggested.append("Use feed_clear_apply(scope='category', target=…) to declutter.")
        if any((a.get("personalized_score") or 0) > 5.0 for a in articles[:10]):
            suggested.append("High-priority items detected — consider article_open on them first.")
        return {"total_unread": total, "by_group": groups, "suggested_actions": suggested}

    @mcp.tool()
    def feed_search(intent: str, limit: int = 10) -> dict[str, Any]:
        """Search articles by natural-language intent (matches title + categories).

        Use for queries like 'IA esta semana', 'tema Chile', 'finance'.

        Returns: {count, articles[]} (slim).
        """
        articles = get_articles(query=intent, limit=min(limit, 100))
        return {"count": len(articles), "articles": [slim_article(a) for a in articles]}

    @mcp.tool()
    def article_open(id: int, with_summary: bool = True) -> dict[str, Any]:
        """Open one article with full detail.

        Use after feed_read/feed_search to deep-dive on a single article.
        with_summary=True returns the cached AI summary IF it exists, but
        does NOT generate one (use article_summarize_apply for that — avoids
        hidden cost).

        Returns: {ok, id, title, url, blog, published, is_read, starred,
                  image_url, user_rating, summary, has_cached_summary}.
        """
        with closing(get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT a.id, a.title, a.url, a.published_date, a.is_read,
                       b.name AS blog_name,
                       SUMM.ai_summary AS cached_summary,
                       img.image_url AS og_image,
                       r.rating AS user_rating,
                       s.id AS starred_id
                FROM articles a
                JOIN blogs b ON b.id = a.blog_id
                LEFT JOIN cdaily_summaries SUMM ON SUMM.article_id = a.id
                LEFT JOIN cdaily_article_images img ON img.article_id = a.id
                LEFT JOIN cdaily_article_ratings r ON r.article_id = a.id
                LEFT JOIN cdaily_starred s ON s.article_id = a.id
                WHERE a.id = ?
                """,
                (id,),
            )
            row = cur.fetchone()
        if not row:
            return {"ok": False, "error": f"Article {id} not found"}
        return {
            "ok": True,
            "id": row["id"],
            "title": row["title"],
            "url": row["url"],
            "blog": row["blog_name"],
            "published": row["published_date"],
            "is_read": bool(row["is_read"]),
            "starred": row["starred_id"] is not None,
            "image_url": row["og_image"],
            "user_rating": row["user_rating"],
            "summary": row["cached_summary"] if with_summary else None,
            "has_cached_summary": bool(row["cached_summary"]),
        }

    # ─── Acciones (mutating, sufijo _apply) ──────────────────────────────

    @mcp.tool()
    def article_mark_apply(id: int, state: str) -> dict[str, Any]:
        """[MUTATES] Change article state.

        Args:
            id: article id.
            state: 'read' | 'unread' | 'starred' | 'unstarred'.
                   starred/unstarred toggle — returns the new boolean.
        """
        if state == "read":
            mark_read(id)
            return {"ok": True, "id": id, "state": "read"}
        if state == "unread":
            mark_unread(id)
            return {"ok": True, "id": id, "state": "unread"}
        if state in ("starred", "unstarred"):
            new = toggle_star(id)
            return {"ok": True, "id": id, "starred": new}
        return {"ok": False, "error": f"Unknown state: {state}"}

    @mcp.tool()
    def article_rate_apply(id: int, rating: int | None) -> dict[str, Any]:
        """[MUTATES] Set rating 1-5 or null to clear.

        Ratings feed the personalized_score that reorders the default feed.
        """
        if rating is not None and not (1 <= rating <= 5):
            return {"ok": False, "error": "rating must be 1-5 or null"}
        new = set_article_rating(id, rating)
        return {"ok": True, "id": id, "rating": new}

    @mcp.tool()
    async def article_summarize_apply(id: int) -> dict[str, Any]:
        """[MUTATES, COSTLY] Generate and cache an AI summary (2-10s).

        Idempotent: subsequent calls return the cached value. Requires
        ai_preferences.enabled=true in config.yaml; fails gracefully with
        a clear error if disabled.
        """
        ai_prefs = CONFIG.get("ai_preferences", {})
        return await summarize_article(id, ai_prefs)

    @mcp.tool()
    def feed_clear_apply(scope: str = "all", target: str | None = None) -> dict[str, Any]:
        """[MUTATES] Bulk mark as read.

        Args:
            scope: 'all' (everything unread), 'category' (require target),
                   or 'blog' (require target).
            target: category name or blog name when scope != 'all'.
        """
        if scope == "all":
            count = mark_all_read()
            return {"ok": True, "marked": count, "scope": "all"}
        if scope in ("category", "blog") and target:
            articles = get_articles(
                unread_only=True,
                limit=500,
                category=target if scope == "category" else None,
            )
            marked: list[int] = []
            for a in articles:
                if scope == "blog" and a.get("blog_name") != target:
                    continue
                mark_read(a["id"])
                marked.append(a["id"])
            return {"ok": True, "marked": len(marked), "scope": scope, "target": target}
        return {"ok": False, "error": "scope must be 'all' | 'category' | 'blog' (with target)"}

    # ─── Fuentes (blogs) ──────────────────────────────────────────────────

    @mcp.tool()
    def sources_list(verbose: bool = False) -> dict[str, Any]:
        """List configured blog sources. verbose adds feed_url, selector, last_scanned."""
        with closing(get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, url, feed_url, scrape_selector, last_scanned "
                "FROM blogs ORDER BY name ASC"
            )
            rows = cur.fetchall()
        shaper = verbose_blog if verbose else slim_blog
        return {"count": len(rows), "sources": [shaper(dict(r)) for r in rows]}

    @mcp.tool()
    async def sources_add_apply(
        name: str,
        url: str,
        feed_url: str | None = None,
        scrape_selector: str | None = None,
    ) -> dict[str, Any]:
        """[MUTATES] Add a blog source via blogwatcher-cli."""
        return await svc_add_blog(
            name=name, url=url, feed_url=feed_url, scrape_selector=scrape_selector
        )

    @mcp.tool()
    async def sources_remove_apply(blog_id: int) -> dict[str, Any]:
        """[MUTATES] Remove a blog source via blogwatcher-cli."""
        return await svc_remove_blog(blog_id=blog_id)

    # ─── Sistema ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def feed_scan_apply() -> dict[str, Any]:
        """[MUTATES, SLOW 30s-2min] Trigger blogwatcher-cli scan.

        Synchronous — the agent waits. Returns {ok, stdout, stderr, returncode}
        on success; {ok: false, error} on failure.
        """
        return await run_scan()

    @mcp.tool()
    def feed_stats() -> dict[str, Any]:
        """Snapshot of unread counts: total + breakdown by category."""
        return get_stats()

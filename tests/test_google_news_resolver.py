"""Tests for Google News resolution and anti-bot fail-fast in article_summary.

These exercise the real code paths against the live network where Google News
is concerned, so a Google RPC change surfaces as a failing test rather than a
silent regression in the UI.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

import httpx
import pytest

from cdaily.services.google_news_resolver import (
    is_google_news_url,
    resolve_google_news_url,
)
from cdaily.services.article_summary import _ArticleBlocked, _fetch_article_text

DB = Path(os.environ.get("CDAILY_DB_PATH", Path.home() / ".blogwatcher-cli" / "blogwatcher-cli.db"))


def _a_google_news_url() -> str | None:
    if not DB.exists():
        return None
    con = sqlite3.connect(DB)
    try:
        row = con.execute("SELECT url FROM articles WHERE url LIKE '%news.google.com/rss/articles%' LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        con.close()


def test_is_google_news_url_detects():
    assert is_google_news_url("https://news.google.com/rss/articles/CBMiABC?hl=es")
    assert is_google_news_url("https://news.google.com/read/CBMiABC")
    assert not is_google_news_url("https://www.nytimes.com/foo")
    assert not is_google_news_url("not a url")


@pytest.mark.network
def test_resolve_google_news_url_live():
    url = _a_google_news_url()
    if url is None:
        pytest.skip("no Google News article in DB")

    async def run():
        async with httpx.AsyncClient(timeout=15.0) as cl:
            return await resolve_google_news_url(cl, url)

    resolved = asyncio.run(run())
    assert resolved is not None, "Google News URL failed to resolve"
    assert resolved.startswith("http")
    assert "news.google.com" not in resolved


@pytest.mark.network
def test_fetch_article_blocked_raises_article_blocked(monkeypatch):
    # Simulate a 403 from the publisher so the fail-fast path is exercised
    # deterministically (real sites vary: 403 one day, 200 the next).
    class _Resp:
        status_code = 403
        headers = {}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("403", request=None, response=self)

        @property
        def is_redirect(self):
            return False

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("cdaily.services.article_summary.httpx.AsyncClient", lambda *a, **k: _Client())

    async def run():
        await _fetch_article_text("https://www.nytimes.com/2026/10/07/world.html")

    with pytest.raises(_ArticleBlocked):
        asyncio.run(run())

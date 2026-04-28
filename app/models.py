# models.py — Pydantic models for request/response validation

from datetime import datetime
from typing import Optional


class ArticleResponse:
    """Outgoing article representation."""
    def __init__(
        self,
        id: int,
        title: str,
        url: str,
        summary: str,
        published_at: Optional[str],
        is_read: bool,
        is_starred: bool,
        blog_name: str,
        category: str,
        emoji: str,
    ):
        self.id = id
        self.title = title
        self.url = url
        self.summary = summary
        self.published_at = published_at
        self.is_read = is_read
        self.is_starred = is_starred
        self.blog_name = blog_name
        self.category = category
        self.emoji = emoji


class ArticlesListResponse:
    """Response for /api/articles."""
    def __init__(self, articles: list[ArticleResponse], count: int):
        self.articles = articles
        self.count = count


class StatsResponse:
    """Response for /api/stats."""
    def __init__(self, total: int, by_category: dict[str, int]):
        self.total = total
        self.by_category = by_category


class ActionResponse:
    """Generic ok/error response."""
    def __init__(self, ok: bool, **kwargs):
        self.ok = ok
        for k, v in kwargs.items():
            setattr(self, k, v)

# models.py — Pydantic schemas for request/response validation

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ArticleOut(BaseModel):
    """Outgoing article representation."""

    id: int
    title: str
    url: str
    summary: str
    published_date: Optional[str] = None
    is_read: bool
    is_starred: bool
    blog_name: str
    category: str
    emoji: str
    image_url: Optional[str] = None
    user_rating: Optional[int] = None
    personalized_score: Optional[float] = None


class ArticlesList(BaseModel):
    articles: list[ArticleOut]
    count: int


class StatsOut(BaseModel):
    total: int
    by_category: dict[str, int]


class ActionOut(BaseModel):
    ok: bool
    count: int = 0


class RatingIn(BaseModel):
    """Rating payload for POST /articles/{id}/rate."""

    rating: Optional[int] = Field(None, ge=1, le=5)


class SummaryOut(BaseModel):
    ok: bool
    summary: Optional[str] = None
    cached: Optional[bool] = None
    error: Optional[str] = None


class TranslationOut(BaseModel):
    ok: bool
    translation: Optional[str] = None
    error: Optional[str] = None


class ScanOut(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    error: Optional[str] = None


class AISettingsIn(BaseModel):
    enabled: bool
    endpoint: str
    api_key: Optional[str] = ""
    auth_type: Optional[str] = "none"
    auth_header_name: Optional[str] = ""
    model: str
    system_prompt: str
    max_content_chars: int
    preferred_language: str = Field(default="English")


class BlogIn(BaseModel):
    name: str
    url: str
    feed_url: Optional[str] = None
    scrape_selector: Optional[str] = None


class BlogOut(BaseModel):
    id: int
    name: str
    url: str
    feed_url: Optional[str] = None
    scrape_selector: Optional[str] = None
    last_scanned: Optional[str] = None

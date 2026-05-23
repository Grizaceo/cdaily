"""Payload shapers — slim by default, verbose opt-in.

Slim responses keep agents token-efficient; verbose adds fields useful
when an agent decides to deep-dive on a single artifact.
"""

from __future__ import annotations

from typing import Any


def slim_article(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": a["id"],
        "title": a["title"],
        "blog": a["blog_name"],
        "published": a.get("published_date"),
        "starred": a.get("is_starred", False),
        "rating": a.get("user_rating"),
        "category": a.get("category"),
    }


def verbose_article(a: dict[str, Any]) -> dict[str, Any]:
    return {
        **slim_article(a),
        "url": a["url"],
        "summary": a.get("summary"),
        "categories": a.get("categories", []),
        "image_url": a.get("image_url"),
        "personalized_score": a.get("personalized_score"),
        "emoji": a.get("emoji"),
        "is_read": a.get("is_read"),
    }


def slim_blog(b: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": b["id"],
        "name": b["name"],
        "url": b.get("url"),
    }


def verbose_blog(b: dict[str, Any]) -> dict[str, Any]:
    return {
        **slim_blog(b),
        "feed_url": b.get("feed_url"),
        "scrape_selector": b.get("scrape_selector"),
        "last_scanned": b.get("last_scanned"),
    }

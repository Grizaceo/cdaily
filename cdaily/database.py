"""Compatibility shim for older imports.

Prefer importing from app.repositories.* directly.
"""

from __future__ import annotations

from .repositories.articles import (  # noqa: F401
    get_article_og_image,
    get_article_url_and_summary,
    get_articles,
    get_articles_missing_images,
    mark_all_read,
    mark_read,
    mark_unread,
    save_ai_summary,
    save_article_og_image,
    set_article_rating,
    toggle_star,
)
from .repositories.bootstrap import get_connection, init_db, validate_db_schema  # noqa: F401
from .repositories.personalization import (  # noqa: F401
    get_blog_category,
    get_blog_category_map,
    get_emoji,
    get_personalization_profile,
)
from .repositories.stats import get_stats  # noqa: F401

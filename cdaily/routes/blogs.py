"""Blogs management routes."""

from __future__ import annotations

from contextlib import closing
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from ..database import get_connection
from ..models import BlogIn, BlogOut
from ..rate_limiter import limiter
from ..services.blogs import add_blog, remove_blog

router = APIRouter(prefix="/api/blogs", tags=["blogs"])


@router.get("", response_model=list[BlogOut])
def get_all_blogs():
    """Retrieve all tracked blogs directly from the database."""
    try:
        with closing(get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, url, feed_url, scrape_selector, last_scanned FROM blogs ORDER BY name ASC"
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_blog(payload: BlogIn, request: Request):
    """Add a new blog to track using blogwatcher-cli."""
    res = await add_blog(
        name=payload.name,
        url=payload.url,
        feed_url=payload.feed_url,
        scrape_selector=payload.scrape_selector,
    )
    if not res.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("error", "Failed to add blog"),
        )
    return {"ok": True, "message": "Blog added successfully"}


@router.delete("/{blog_id}")
@limiter.limit("10/minute")
async def delete_blog(blog_id: int, request: Request):
    """Remove a blog from tracking using blogwatcher-cli."""
    res = await remove_blog(blog_id=blog_id)
    if not res.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("error", "Failed to remove blog"),
        )
    return {"ok": True, "message": "Blog removed successfully"}

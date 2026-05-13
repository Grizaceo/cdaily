"""Article-related HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..config import CONFIG
from ..database import get_articles, mark_all_read, mark_read, mark_unread, set_article_rating, toggle_star
from ..services.article_images import fetch_article_image
from ..services.article_summary import summarize_article

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("")
def api_articles(
    cat: str | None = Query(None, description="Category filter"),
    q: str | None = Query(None, description="Search query"),
    unread: bool = Query(False, description="Only unread"),
    starred: bool = Query(False, description="Only starred"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    articles = get_articles(
        category=cat,
        query=q,
        unread_only=unread,
        starred=starred,
        limit=limit,
        offset=offset,
    )
    return {"articles": articles, "count": len(articles)}


@router.post("/{article_id}/read")
def api_mark_read(article_id: int):
    mark_read(article_id)
    return {"ok": True}


@router.post("/{article_id}/unread")
def api_mark_unread(article_id: int):
    mark_unread(article_id)
    return {"ok": True}


@router.post("/{article_id}/star")
def api_toggle_star(article_id: int):
    starred = toggle_star(article_id)
    return {"ok": True, "starred": starred}


@router.post("/{article_id}/summarize")
async def api_summarize(article_id: int):
    ai_prefs = CONFIG.get("ai_preferences", {})
    result = await summarize_article(article_id, ai_prefs)
    if not result.get("ok"):
        error = result.get("error", "Unknown error")
        if error == "AI summarization is disabled in config.":
            raise HTTPException(status_code=400, detail=error)
    return result


@router.post("/{article_id}/rate")
def api_rate_article(article_id: int, payload: dict):
    rating_raw = payload.get("rating")
    if rating_raw is None:
        rating = None
    else:
        try:
            rating = int(rating_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="rating must be an integer between 1 and 5, or null")
        if rating < 1 or rating > 5:
            raise HTTPException(status_code=400, detail="rating must be between 1 and 5")

    new_rating = set_article_rating(article_id, rating)
    return {"ok": True, "rating": new_rating}


@router.post("/read-all")
def api_mark_all_read():
    count = mark_all_read()
    return {"ok": True, "count": count}


@router.get("/{article_id}/image")
async def api_article_image(article_id: int):
    return await fetch_article_image(article_id)

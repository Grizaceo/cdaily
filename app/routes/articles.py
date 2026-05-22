"""Article-related HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..config import CONFIG
from ..database import get_articles, mark_all_read, mark_read, mark_unread, set_article_rating, toggle_star
from ..models import ActionOut, ArticlesList, RatingIn, SummaryOut
from ..rate_limiter import limiter
from ..services.article_images import fetch_article_image
from ..services.article_summary import summarize_article

router = APIRouter(prefix="/api/articles", tags=["articles"])

# Rate limits
_RATE_FAST = "60/minute"
_RATE_SLOW = "10/minute"
_RATE_BULK = "5/minute"


@router.get("", response_model=ArticlesList)
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


@router.post("/{article_id}/read", response_model=ActionOut)
@limiter.limit(_RATE_FAST)
def api_mark_read(article_id: int, request: Request):
    mark_read(article_id)
    return {"ok": True}


@router.post("/{article_id}/unread", response_model=ActionOut)
@limiter.limit(_RATE_FAST)
def api_mark_unread(article_id: int, request: Request):
    mark_unread(article_id)
    return {"ok": True}


@router.post("/{article_id}/star")
@limiter.limit(_RATE_FAST)
def api_toggle_star(article_id: int, request: Request):
    starred = toggle_star(article_id)
    return {"ok": True, "starred": starred}


@router.post("/{article_id}/summarize", response_model=SummaryOut)
@limiter.limit(_RATE_SLOW)
async def api_summarize(article_id: int, request: Request):
    ai_prefs = CONFIG.get("ai_preferences", {})
    result = await summarize_article(article_id, ai_prefs)
    if not result.get("ok"):
        error = result.get("error", "Unknown error")
        if "disabled" in error.lower():
            raise HTTPException(status_code=400, detail=error)
    return result


@router.post("/{article_id}/rate")
@limiter.limit(_RATE_FAST)
def api_rate_article(article_id: int, payload: RatingIn, request: Request):
    new_rating = set_article_rating(article_id, payload.rating)
    return {"ok": True, "rating": new_rating}


@router.post("/read-all", response_model=ActionOut)
@limiter.limit(_RATE_BULK)
def api_mark_all_read(request: Request):
    count = mark_all_read()
    return {"ok": True, "count": count}


@router.get("/{article_id}/image")
@limiter.limit(_RATE_SLOW)
async def api_article_image(article_id: int, request: Request):
    return await fetch_article_image(article_id)

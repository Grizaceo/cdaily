"""
main.py — CDaily FastAPI application.
Serves the feed UI and provides a JSON API backed by blogwatcher-cli SQLite.
"""

import subprocess
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import CONFIG
from .database import (
    get_articles,
    get_article_url_and_summary,
    get_stats,
    init_db,
    mark_all_read,
    mark_read,
    mark_unread,
    save_ai_summary,
    save_article_og_image,
    toggle_star,
)

# ── App bootstrap ─────────────────────────────────────────────────────────────

init_db()

BASE_DIR = Path(__file__).parent
app = FastAPI(title="CDaily", description="Cristóbal's Daily Feed")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    Renders the main feed page.
    Category filter passed via query param ?cat=...
    """
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"config": CONFIG}
    )


@app.get("/api/articles")
def api_articles(
    cat: str | None = Query(None, description="Category filter"),
    q: str | None = Query(None, description="Search query"),
    unread: bool = Query(False, description="Only unread"),
    starred: bool = Query(False, description="Only starred"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    JSON endpoint for article list.
    Used by the frontend for dynamic filtering without page reload.
    """
    articles = get_articles(
        category=cat,
        query=q,
        unread_only=unread,
        starred=starred,
        limit=limit,
        offset=offset,
    )
    return {"articles": articles, "count": len(articles)}


@app.post("/api/articles/{article_id}/read")
def api_mark_read(article_id: int):
    mark_read(article_id)
    return {"ok": True}


@app.post("/api/articles/{article_id}/unread")
def api_mark_unread(article_id: int):
    mark_unread(article_id)
    return {"ok": True}


@app.post("/api/articles/{article_id}/star")
def api_toggle_star(article_id: int):
    starred = toggle_star(article_id)
    return {"ok": True, "starred": starred}


@app.post("/api/articles/{article_id}/summarize")
async def api_summarize(article_id: int):
    ai_prefs = CONFIG.get("ai_preferences", {})
    if not ai_prefs.get("enabled"):
        raise HTTPException(status_code=400, detail="AI summarization is disabled in config.")
        
    url, existing_summary = get_article_url_and_summary(article_id)
    if existing_summary:
        return {"ok": True, "summary": existing_summary, "cached": True}
        
    if not url:
        return {"ok": False, "error": "Article has no URL to summarize."}
        
    # Fetch content from URL
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html_content = resp.text

            # Extract og:image
            og_image = extract_og_image(html_content)
            if og_image:
                from .database import save_article_og_image
                save_article_og_image(article_id, og_image)

            # Extract plain text
            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)

    except Exception as e:
        return {"ok": False, "error": f"Failed to fetch article: {str(e)}"}

    if not content:
        return {"ok": False, "error": "Could not extract text from article."}

    endpoint = ai_prefs.get("endpoint")
    model = ai_prefs.get("model")
    system_prompt = ai_prefs.get("system_prompt", "Summarize this.")
    
    # Truncate slightly to avoid memory blowouts on huge articles
    content_truncated = content[:30000] 
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_truncated}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            
            save_ai_summary(article_id, summary)
            return {"ok": True, "summary": summary, "cached": False}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/articles/read-all")
def api_mark_all_read():
    count = mark_all_read()
    return {"ok": True, "count": count}


@app.post("/api/scan")
def api_scan():
    """
    Runs blogwatcher-cli scan in the foreground.
    Returns summary of what was found.
    """
    try:
        result = subprocess.run(
            ["blogwatcher-cli", "scan"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "ok": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Scan timed out (>120s)"}
    except FileNotFoundError:
        return {"ok": False, "error": "blogwatcher-cli not found in PATH"}


@app.get("/api/stats")
def api_stats():
    stats = get_stats()
    return stats


@app.get("/api/articles/{article_id}/image")
async def api_article_image(article_id: int):
    """
    Returns article image URL. If not cached, fetches the page and extracts OG image.
    Returns {image_url: str|null, cached: bool}
    """
    from .database import get_article_og_image
    cached = get_article_og_image(article_id)
    if cached is not None:
        return {"image_url": cached, "cached": True}

    url, _ = get_article_url_and_summary(article_id)
    if not url:
        return {"image_url": None, "cached": False, "error": "No URL"}

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            og_image = extract_og_image(resp.text)
            save_article_og_image(article_id, og_image)
            return {"image_url": og_image, "cached": False}
    except Exception as e:
        return {"image_url": None, "cached": False, "error": str(e)}


# ── Helpers ────────────────────────────────────────────────────────────────────

def extract_og_image(html: str) -> str | None:
    """Try to extract the og:image meta tag from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    # Try og:image first
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"].strip()
    # Fallback: twitter:image
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return tw["content"].strip()
    return None


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=CONFIG["host"],
        port=CONFIG["port"],
        reload=False,
    )

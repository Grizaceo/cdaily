"""
main.py — CDaily FastAPI application.
Serves the feed UI and provides a JSON API backed by blogwatcher-cli SQLite.
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import CONFIG
from .database import (
    get_articles,
    get_articles_missing_images,
    get_article_url_and_summary,
    get_stats,
    init_db,
    mark_all_read,
    mark_read,
    mark_unread,
    save_ai_summary,
    save_article_og_image,
    set_article_rating,
    toggle_star,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
    return templates.TemplateResponse(request=request, name="index.html", context={"config": CONFIG})


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

    # Truncate to avoid exceeding AI server context (n_ctx)
    max_chars = ai_prefs.get("max_content_chars", 12000)
    content_truncated = content[:max_chars]

    logging.info(
        f"Summarizing article {article_id} ({len(content)} chars) using model {model}. "
        f"Sending {len(content_truncated)} chars."
    )
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": content_truncated}],
        "temperature": 0.7,
        "presence_penalty": 0.6,
        "max_tokens": 500,
    }

    headers = {"Content-Type": "application/json"}
    api_key = ai_prefs.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code != 200:
                error_body = response.text
                logging.error(f"AI Server Error ({response.status_code}): {error_body}")
                return {"ok": False, "error": f"AI Server Error {response.status_code}: {error_body}"}

            data = response.json()
            summary = extract_summary_text(data)
            if not summary:
                logging.error("AI response has no summary text: %s", data)
                return {"ok": False, "error": "La IA respondió sin contenido de resumen."}
            logging.info(f"AI Summary for {article_id}: {summary[:100]}...")

            save_ai_summary(article_id, summary)
            return {"ok": True, "summary": summary, "cached": False}
    except Exception as e:
        logging.exception("Exception during AI summarization")
        return {"ok": False, "error": str(e)}


@app.post("/api/articles/{article_id}/rate")
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


@app.post("/api/articles/read-all")
def api_mark_all_read():
    count = mark_all_read()
    return {"ok": True, "count": count}


@app.post("/api/scan")
async def api_scan(background_tasks: BackgroundTasks):
    """
    Runs blogwatcher-cli scan asynchronously.
    Then schedules background image fetching for new articles.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "blogwatcher-cli", "scan",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=120.0)
            stdout = stdout_bytes.decode() if stdout_bytes else ""
            stderr = stderr_bytes.decode() if stderr_bytes else ""
            returncode = proc.returncode
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"ok": False, "error": "Scan timed out (>120s)"}

        # Schedule background image fetching
        background_tasks.add_task(fetch_missing_images)

        return {
            "ok": True,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }
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


async def fetch_missing_images(limit: int = 50):
    """
    Background task to fetch and cache images for articles that don't have one.
    """
    articles = get_articles_missing_images(limit=limit)
    if not articles:
        return

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        for art in articles:
            try:
                resp = await client.get(art["url"], headers=headers)
                if resp.status_code == 200:
                    og_image = extract_og_image(resp.text)
                    save_article_og_image(art["id"], og_image)
                else:
                    # Mark as attempted
                    save_article_og_image(art["id"], None)
            except Exception:
                # Silently ignore fetch errors in background
                save_article_og_image(art["id"], None)
            # Rate limiting: wait 1 second between requests
            await asyncio.sleep(1)


def extract_og_image(html: str) -> str | None:
    """Try to extract the og:image meta tag from HTML with more aggressive fallbacks."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Try og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"].strip()

    # 2. Try twitter:image
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return tw["content"].strip()

    # 3. Fallback: first large-ish image in article body (if any)
    # This is a bit heuristic, but better than nothing.
    # Look for <img> tags that don't look like icons/tracking pixels.
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
            
        # Check dimensions if specified
        try:
            width = int(img.get("width", "100"))
            height = int(img.get("height", "100"))
            if width <= 50 or height <= 50:
                continue
        except ValueError:
            pass

        # Skip small icons/placeholders
        if any(x in src.lower() for x in ["icon", "logo", "tracker", "pixel", "avatar"]):
            continue
        # Return the first absolute URL or meaningful relative URL
        if src.startswith("http"):
            return src

    return None


def extract_summary_text(response_data: dict[str, Any]) -> str:
    """
    Extracts summary text from OpenAI-compatible response payloads.
    Handles common variants from local inference gateways.
    """
    choices = response_data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    # Some APIs return content parts, e.g. [{"type":"text","text":"..."}]
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text")
                            if isinstance(text, str):
                                parts.append(text)
                    return "\n".join(p.strip() for p in parts if p.strip()).strip()
            text = first.get("text")
            if isinstance(text, str):
                return text.strip()
    return ""


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=CONFIG["host"],
        port=CONFIG["port"],
        reload=False,
    )

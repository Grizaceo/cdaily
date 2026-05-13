"""Article image extraction and cache service."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..database import (
    get_article_url_and_summary,
    get_articles_missing_images,
    get_article_og_image,
    save_article_og_image,
)
from ..validate_url import validate_url


async def fetch_article_image(article_id: int) -> dict[str, Any]:
    cached = get_article_og_image(article_id)
    if cached is not None:
        return {"image_url": cached, "cached": True}

    url, _ = get_article_url_and_summary(article_id)
    if not url:
        return {"image_url": None, "cached": False, "error": "No URL"}

    # SSRF guard
    try:
        validate_url(url)
    except ValueError as e:
        return {"image_url": None, "cached": False, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            og_image = extract_og_image(resp.text)
            save_article_og_image(article_id, og_image)
            return {"image_url": og_image, "cached": False}
    except Exception as exc:
        return {"image_url": None, "cached": False, "error": str(exc)}


async def fetch_missing_images(limit: int = 50) -> None:
    """Background task to fetch and cache images for articles that don't have one."""
    articles = get_articles_missing_images(limit=limit)
    if not articles:
        return

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        for art in articles:
            try:
                # Validate each URL before fetching
                try:
                    validate_url(art["url"])
                except ValueError:
                    save_article_og_image(art["id"], None)
                    await asyncio.sleep(1)
                    continue
                resp = await client.get(art["url"], headers=headers)
                if resp.status_code == 200:
                    og_image = extract_og_image(resp.text)
                    save_article_og_image(art["id"], og_image)
                else:
                    save_article_og_image(art["id"], None)
            except Exception:
                save_article_og_image(art["id"], None)
            await asyncio.sleep(1)


def extract_og_image(html: str) -> str | None:
    """Try to extract the og:image meta tag from HTML with fallbacks."""
    soup = BeautifulSoup(html, "html.parser")

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"].strip()

    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return tw["content"].strip()

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue

        try:
            width = int(img.get("width", "100"))
            height = int(img.get("height", "100"))
            if width <= 50 or height <= 50:
                continue
        except ValueError:
            pass

        if any(x in src.lower() for x in ["icon", "logo", "tracker", "pixel", "avatar"]):
            continue
        if src.startswith("http"):
            return src

    return None

"""Article image extraction and cache service."""

from __future__ import annotations

import asyncio
from typing import Any
import urllib.parse

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
    exists, cached = get_article_og_image(article_id)
    if exists:
        return {"image_url": cached, "cached": True}

    url, _ = get_article_url_and_summary(article_id)
    if not url:
        return {"image_url": None, "cached": False, "error": "No URL"}

    # SSRF guard
    try:
        validate_url(url)
    except ValueError as e:
        save_article_og_image(article_id, None)
        return {"image_url": None, "cached": False, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            og_image = extract_og_image(resp.text, base_url=url)
            save_article_og_image(article_id, og_image)
            return {"image_url": og_image, "cached": False}
    except Exception as exc:
        save_article_og_image(article_id, None)
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
                    og_image = extract_og_image(resp.text, base_url=art["url"])
                    save_article_og_image(art["id"], og_image)
                else:
                    save_article_og_image(art["id"], None)
            except Exception:
                save_article_og_image(art["id"], None)
            await asyncio.sleep(1)


def extract_og_image(html: str, base_url: str | None = None) -> str | None:
    """Try to extract the og:image meta tag from HTML with fallbacks, resolving relative URLs."""
    soup = BeautifulSoup(html, "html.parser")

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        raw_url = og["content"].strip()
        if base_url:
            return urllib.parse.urljoin(base_url, raw_url)
        return raw_url

    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        raw_url = tw["content"].strip()
        if base_url:
            return urllib.parse.urljoin(base_url, raw_url)
        return raw_url

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

        resolved_src = src.strip()
        if base_url:
            resolved_src = urllib.parse.urljoin(base_url, resolved_src)
        if resolved_src.startswith("http"):
            return resolved_src

    return None

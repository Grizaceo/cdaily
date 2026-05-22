"""Article summarization service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..database import get_article_url_and_summary, save_ai_summary, save_article_og_image
from .article_images import extract_og_image
from ..validate_url import validate_url

logger = logging.getLogger(__name__)


async def summarize_article(article_id: int, ai_prefs: dict[str, Any]) -> dict[str, Any]:
    if not ai_prefs.get("enabled"):
        return {"ok": False, "error": "AI summarization is disabled in config."}

    url, existing_summary = get_article_url_and_summary(article_id)
    if existing_summary:
        return {"ok": True, "summary": existing_summary, "cached": True}

    if not url:
        return {"ok": False, "error": "Article has no URL to summarize."}

    # SSRF guard
    try:
        validate_url(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html_content = resp.text

            og_image = extract_og_image(html_content)
            if og_image:
                save_article_og_image(article_id, og_image)

            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to fetch article: {exc}"}

    if not content:
        return {"ok": False, "error": "Could not extract text from article."}

    endpoint = ai_prefs.get("endpoint")
    model = ai_prefs.get("model")
    system_prompt = ai_prefs.get("system_prompt", "Summarize this.")
    max_chars = ai_prefs.get("max_content_chars", 12000)
    content_truncated = content[:max_chars]

    logger.info(
        "Summarizing article %s (%s chars) using model %s. Sending %s chars.",
        article_id,
        len(content),
        model,
        len(content_truncated),
    )
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": content_truncated}],
        "temperature": 0.7,
        "presence_penalty": 0.6,
        "max_tokens": 500,
    }

    # AI endpoint: validate URL too (comes from config, not user, but defense in depth)
    try:
        validate_url(endpoint)
    except ValueError:
        return {"ok": False, "error": "AI endpoint URL is invalid or points to a private/internal host."}

    headers = {"Content-Type": "application/json"}
    auth_type = ai_prefs.get("auth_type", "bearer")
    api_key = ai_prefs.get("api_key", "")
    if api_key and auth_type != "none":
        if auth_type == "custom":
            header_name = ai_prefs.get("auth_header_name", "Authorization")
            headers[header_name] = api_key
        else:
            # Default or explicit bearer
            headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code != 200:
                error_body = response.text
                logger.error("AI Server Error (%s): body length=%s", response.status_code, len(error_body))
                return {"ok": False, "error": f"AI Server Error {response.status_code}: {error_body}"}

            data = response.json()
            summary = extract_summary_text(data)
            if not summary:
                logger.error(
                    "AI response has no summary text (status=%s, body length=%s)",
                    response.status_code,
                    len(response.text),
                )
                return {"ok": False, "error": "La IA respondió sin contenido de resumen."}

            logger.info("AI Summary for %s: %s...", article_id, summary[:100])
            save_ai_summary(article_id, summary)
            return {"ok": True, "summary": summary, "cached": False}
    except Exception as exc:
        logger.exception("Exception during AI summarization")
        return {"ok": False, "error": str(exc)}


def extract_summary_text(response_data: dict[str, Any]) -> str:
    """Extract summary text from OpenAI-compatible payloads."""
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
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text")
                            if isinstance(text, str):
                                parts.append(text)
                    return "\n".join(piece.strip() for piece in parts if piece.strip()).strip()
            text = first.get("text")
            if isinstance(text, str):
                return text.strip()
    return ""

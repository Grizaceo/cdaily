"""Article summarization and translation service."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..database import get_article_url_and_summary, save_ai_summary, save_article_og_image
from .article_images import extract_og_image
from ..validate_url import validate_url

logger = logging.getLogger(__name__)

# Patterns that commonly appear in provider error bodies when a credential is the
# problem (e.g. "Invalid API key: sk-..." or "token abc123"). Matching raw values are
# redacted before the body is ever surfaced to the client.
_SECRET_RE = re.compile(
    r"(?i)"
    r"(sk-[A-Za-z0-9_\-]{6,})"
    r"|(api[_-]?key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,})"
    r"|(token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,})"
    r"|(Bearer\s+[A-Za-z0-9_\-\.]{8,})"
    r"|(AKIA[0-9A-Z]{12,})"
    r"|([A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})"  # JWT-like / dotted secrets
)
_ERROR_BODY_MAX_CHARS = 200


def _redact_error_body(body: str) -> str:
    """Truncate and redact an AI provider error body before surfacing it to the client.

    Provider 4xx responses sometimes echo the API key / token back in the body (e.g. a
    401 "Invalid API key: sk-..."). We cap length and mask credential-shaped substrings
    so secrets never propagate to the CDaily client.
    """
    if not body:
        return body
    redacted = _SECRET_RE.sub("[REDACTED]", body)
    if len(redacted) > _ERROR_BODY_MAX_CHARS:
        redacted = redacted[:_ERROR_BODY_MAX_CHARS] + "... [truncated]"
    return redacted


async def _fetch_article_text(url: str, article_id: int | None = None) -> tuple[str, str | None]:
    """Fetch and extract readable text from an article URL.

    SSRF hardening (S3): the initial URL is validated by the caller, but every
    redirect hop must also be re-validated so a public URL cannot 301/302 to an
    internal/cloud-metadata address. We disable httpx auto-follow and walk the
    redirect chain ourselves, calling validate_url() on each destination host.
    """
    og_image = None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        # follow_redirects=False so we control and re-validate each hop.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            current_url = url
            resp = None
            # Bound the number of redirects to avoid infinite loops.
            for _ in range(10):
                resp = await client.get(current_url, headers=headers)
                if resp.is_redirect and "location" in resp.headers:
                    # Re-validate the next hop's host (SSRF guard per redirect).
                    validate_url(resp.headers["location"])
                    current_url = resp.headers["location"]
                    continue
                break
            if resp is None:
                raise RuntimeError("No response received while fetching article.")
            resp.raise_for_status()
            html_content = resp.text

            og_image = extract_og_image(html_content)
            if og_image and article_id is not None:
                save_article_og_image(article_id, og_image)

            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch article: {exc}") from exc

    if not content:
        raise RuntimeError("Could not extract text from article.")

    return content, og_image


async def _request_ai_completion(endpoint: str, payload: dict[str, Any], ai_prefs: dict[str, Any]) -> str:
    """Send a request to the configured OpenAI-compatible endpoint.

    Retries transient failures (connection errors, timeouts, 5xx) with bounded
    exponential backoff. Non-retryable failures (4xx client errors, invalid URL)
    return immediately so the user gets a clear error rather than a long stall.
    """
    # AI endpoint: validate URL too (comes from config, not user, but defense in depth)
    try:
        validate_url(endpoint, allow_private=True)
    except ValueError as exc:
        raise RuntimeError("AI endpoint URL is invalid or points to an invalid host.") from exc

    headers = {"Content-Type": "application/json"}
    auth_type = ai_prefs.get("auth_type", "bearer")
    api_key = ai_prefs.get("api_key", "")
    if api_key and auth_type != "none":
        if auth_type == "custom":
            header_name = ai_prefs.get("auth_header_name", "Authorization")
            headers[header_name] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    if endpoint and "openrouter.ai" in endpoint.lower():
        headers["HTTP-Referer"] = "https://github.com/Grizaceo/cdaily"
        headers["X-Title"] = "CDaily"

    max_attempts = 3
    base_delay = 1.0
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(endpoint, json=payload, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                # Transient: network down / timeout (e.g. local endpoint not up yet)
                last_exc = exc
                logger.warning("AI request attempt %s/%s failed (transport): %s", attempt, max_attempts, exc)
                if attempt < max_attempts:
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
                continue

            if response.status_code >= 500:
                # Transient server error -> retry
                last_exc = RuntimeError(f"AI Server Error {response.status_code}")
                logger.warning("AI request attempt %s/%s got 5xx (%s)", attempt, max_attempts, response.status_code)
                if attempt < max_attempts:
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
                continue

            if response.status_code != 200:
                error_body = _redact_error_body(response.text)
                logger.error("AI Server Error (%s): body length=%s", response.status_code, len(error_body))
                raise RuntimeError(f"AI Server Error {response.status_code}: {error_body}")

            data = response.json()
            result = extract_summary_text(data)
            if not result:
                logger.error(
                    "AI response has no text content (status=%s, body length=%s)",
                    response.status_code,
                    len(response.text),
                )
                raise RuntimeError("La IA respondió sin contenido de texto.")
            return result

    if last_exc is not None:
        logger.error("AI request exhausted %s attempts", max_attempts)
        raise RuntimeError(f"AI request failed after {max_attempts} attempts: {last_exc}") from last_exc
    raise RuntimeError(f"AI request failed after {max_attempts} attempts")


async def summarize_article(article_id: int, ai_prefs: dict[str, Any]) -> dict[str, Any]:
    if not ai_prefs.get("enabled"):
        return {"ok": False, "error": "AI summarization is disabled in config."}

    url, existing_summary = get_article_url_and_summary(article_id)
    if existing_summary:
        return {"ok": True, "summary": existing_summary, "cached": True}

    if not url:
        return {"ok": False, "error": "Article has no URL to summarize."}

    try:
        validate_url(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    try:
        content, _ = await _fetch_article_text(url, article_id)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

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

    try:
        summary = await _request_ai_completion(endpoint, payload, ai_prefs)
    except Exception as exc:
        logger.exception("Exception during AI summarization")
        return {"ok": False, "error": str(exc)}

    logger.info("AI Summary for %s: %s...", article_id, summary[:100])
    save_ai_summary(article_id, summary)
    return {"ok": True, "summary": summary, "cached": False}


async def translate_article(article_id: int, ai_prefs: dict[str, Any]) -> dict[str, Any]:
    if not ai_prefs.get("enabled"):
        return {"ok": False, "error": "AI translation is disabled in config."}

    url, _ = get_article_url_and_summary(article_id)
    if not url:
        return {"ok": False, "error": "Article has no URL to translate."}

    try:
        validate_url(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    try:
        content, _ = await _fetch_article_text(url, article_id)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    endpoint = ai_prefs.get("endpoint")
    model = ai_prefs.get("model")
    preferred_language = str(ai_prefs.get("preferred_language", "English")).strip() or "English"
    max_chars = ai_prefs.get("max_content_chars", 12000)
    content_truncated = content[:max_chars]

    logger.info(
        "Translating article %s to %s using model %s. Sending %s chars.",
        article_id,
        preferred_language,
        model,
        len(content_truncated),
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"Translate the following text to {preferred_language}. "
                    "Preserve the original meaning, keep line breaks when useful, and return only the translated text."
                ),
            },
            {"role": "user", "content": content_truncated},
        ],
        "temperature": 0.4,
        "presence_penalty": 0.2,
        "max_tokens": 500,
    }

    try:
        translation = await _request_ai_completion(endpoint, payload, ai_prefs)
    except Exception as exc:
        logger.exception("Exception during AI translation")
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "translation": translation}


def extract_summary_text(response_data: dict[str, Any]) -> str:
    """Extract text from OpenAI-compatible payloads."""
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

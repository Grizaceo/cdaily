"""System routes: home page, stats, and scan."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import CONFIG, save_ai_preferences

# Placeholder returned by GET /api/settings instead of the cleartext key.
# The frontend sends it back on save to signal "unchanged" (keep existing key).
API_KEY_MASK = "********"
from ..database import get_stats
from ..models import AISettingsIn
from ..rate_limiter import limiter
from ..services.article_images import fetch_missing_images
from ..services.scan import run_scan
from ..validate_url import validate_url

router = APIRouter(tags=["system"])
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"config": CONFIG})


@router.get("/api/stats")
def api_stats():
    return get_stats()


@router.post("/api/scan")
@limiter.limit("5/minute")
async def api_scan(background_tasks: BackgroundTasks, request: Request):
    result = await run_scan()
    returncode = result.get("returncode")
    ok = bool(result.get("ok")) and (not isinstance(returncode, int) or returncode == 0)
    if not ok:
        return {
            "ok": False,
            "error": result.get("error") or result.get("stderr") or "Unknown scan error",
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "returncode": returncode,
        }

    background_tasks.add_task(fetch_missing_images)
    return {
        "ok": True,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": returncode,
    }


@router.get("/api/settings")
def api_get_settings():
    """Retrieve current AI preferences settings.

    H1 fix: never expose api_key in cleartext. Return a mask placeholder plus a
    boolean flag so the client knows a key is configured without leaking it.
    """
    prefs = CONFIG.get("ai_preferences", {})
    public = dict(prefs)
    raw_key = (public.get("api_key") or "").strip()
    if raw_key:
        public["api_key"] = API_KEY_MASK
        public["has_api_key"] = True
    else:
        public["api_key"] = ""
        public["has_api_key"] = False
    return public


def _settings_auth_required() -> bool:
    """Auth is required only when CDAILY_API_TOKEN is configured (production)."""
    return bool(os.environ.get("CDAILY_API_TOKEN", "").strip())


def _require_settings_auth(request: Request) -> None:
    """Route-level defense-in-depth for write endpoints.

    Mirrors the optional require_auth middleware in main.py: when CDAILY_API_TOKEN
    is set, the client must send `Authorization: Bearer <CDAILY_API_TOKEN>`. When no
    token is configured (default dev), the endpoints stay open.
    """
    if not _settings_auth_required():
        return
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {os.environ.get('CDAILY_API_TOKEN', '').strip()}"
    if auth != expected:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized — provide Authorization: Bearer <CDAILY_API_TOKEN>",
        )


def _resolve_api_key(incoming: str | None) -> str:
    """If the client echoed the mask placeholder back, keep the stored key.

    This lets the settings UI re-save without forcing the user to retype the key,
    while still allowing an explicit empty string to clear it and a new value to replace it.
    """
    if incoming == API_KEY_MASK:
        return (CONFIG.get("ai_preferences", {}).get("api_key") or "").strip()
    return (incoming or "").strip()


@router.post("/api/settings")
@limiter.limit("10/minute")
def api_save_settings(payload: AISettingsIn, request: Request):
    """Save AI preferences settings to config.yaml and reload CONFIG."""
    _require_settings_auth(request)
    try:
        # Validate endpoint URL
        validate_url(payload.endpoint, allow_private=True)
    except ValueError as e:
        return {"ok": False, "error": f"Invalid endpoint: {str(e)}"}

    prefs = payload.model_dump()
    prefs["api_key"] = _resolve_api_key(payload.api_key)
    save_ai_preferences(prefs)
    return {"ok": True}


@router.post("/api/settings/test")
@limiter.limit("10/minute")
async def api_test_settings(payload: AISettingsIn, request: Request):
    """Test AI endpoint connection with the supplied parameters."""
    _require_settings_auth(request)
    endpoint = payload.endpoint
    auth_type = payload.auth_type
    api_key = _resolve_api_key(payload.api_key)
    auth_header_name = payload.auth_header_name
    model = payload.model

    # Validate endpoint URL
    try:
        validate_url(endpoint, allow_private=True)
    except ValueError as e:
        return {"ok": False, "error": f"Invalid endpoint: {str(e)}"}

    # Prepare Headers
    headers = {"Content-Type": "application/json"}
    if api_key and auth_type != "none":
        if auth_type == "custom":
            header_name = auth_header_name or "Authorization"
            headers[header_name] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    if "openrouter.ai" in endpoint.lower():
        headers["HTTP-Referer"] = "https://github.com/Grizaceo/cdaily"
        headers["X-Title"] = "CDaily"

    # Simple completion request to test connection
    test_payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Dí hola de vuelta muy brevemente para confirmar conexión."}
        ],
        "max_tokens": 15,
        "temperature": 0.5,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(endpoint, json=test_payload, headers=headers)
            if response.status_code != 200:
                return {
                    "ok": False,
                    "error": f"Error del servidor de IA (Status {response.status_code}): {response.text[:200]}",
                }

            data = response.json()
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if content:
                            msg = f"Conexión exitosa. La IA respondió: '{content.strip()}'"
                            return {"ok": True, "message": msg}

            return {
                "ok": True,
                "message": "Conexión exitosa, pero respuesta sin formato chat esperado (choices.message.content).",
            }
    except Exception as exc:
        return {"ok": False, "error": f"Error de conexión: {str(exc)}"}

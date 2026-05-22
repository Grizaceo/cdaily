"""System routes: home page, stats, and scan."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import CONFIG, save_ai_preferences
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
    ok = bool(result.get("ok"))
    if not ok:
        return {"ok": False, "error": result.get("error", "Unknown scan error")}

    background_tasks.add_task(fetch_missing_images)
    return {
        "ok": True,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("returncode", 0),
    }


@router.get("/api/settings")
def api_get_settings():
    """Retrieve current AI preferences settings."""
    return CONFIG.get("ai_preferences", {})


@router.post("/api/settings")
@limiter.limit("10/minute")
def api_save_settings(payload: AISettingsIn, request: Request):
    """Save AI preferences settings to config.yaml and reload CONFIG."""
    try:
        # Validate endpoint URL
        validate_url(payload.endpoint, allow_private=True)
    except ValueError as e:
        return {"ok": False, "error": f"Invalid endpoint: {str(e)}"}

    save_ai_preferences(payload.model_dump())
    return {"ok": True}


@router.post("/api/settings/test")
@limiter.limit("10/minute")
async def api_test_settings(payload: AISettingsIn, request: Request):
    """Test AI endpoint connection with the supplied parameters."""
    endpoint = payload.endpoint
    auth_type = payload.auth_type
    api_key = payload.api_key
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
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(endpoint, json=test_payload, headers=headers)
            if response.status_code != 200:
                return {
                    "ok": False,
                    "error": f"Error del servidor de IA (Status {response.status_code}): {response.text[:200]}"
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
                            return {"ok": True, "message": f"Conexión exitosa. La IA respondió: '{content.strip()}'"}
            
            return {"ok": True, "message": "Conexión exitosa, pero la respuesta no tenía el formato de chat esperado (choices.message.content)."}
    except Exception as exc:
        return {"ok": False, "error": f"Error de conexión: {str(exc)}"}


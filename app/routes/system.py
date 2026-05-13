"""System routes: home page, stats, and scan."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import CONFIG
from ..database import get_stats
from ..services.article_images import fetch_missing_images
from ..services.scan import run_scan

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
async def api_scan(background_tasks: BackgroundTasks):
    result = await run_scan()
    if result.get("ok") != 1:
        return {"ok": False, "error": result.get("error", "Unknown scan error")}

    background_tasks.add_task(fetch_missing_images)
    return {
        "ok": True,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "returncode": result.get("returncode", 0),
    }

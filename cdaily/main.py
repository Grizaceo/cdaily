"""CDaily FastAPI application bootstrap."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .config import CONFIG
from .database import init_db
from .rate_limiter import limiter
from .routes.articles import router as articles_router
from .routes.blogs import router as blogs_router
from .routes.system import router as system_router

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent

# --- Lifespan: init DB once at startup (not at import time) ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CDaily", description="Personal Daily Feed", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CSP: basic defense-in-depth — restricts inline styles/scripts
CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' http: https: data:; "
    "script-src 'self'"
)

ALLOWED_ORIGINS = frozenset(
    {
        f"http://127.0.0.1:{CONFIG['port']}",
        f"http://localhost:{CONFIG['port']}",
        f"http://host.docker.internal:{CONFIG['port']}",
    }
)


def _request_origin(request) -> str | None:
    host = request.headers.get("host")
    if not host:
        return None
    return f"{request.url.scheme}://{host}"


# Optional auth token for production deployments.
_AUTH_TOKEN = os.environ.get("CDAILY_API_TOKEN", "")


@app.middleware("http")
async def add_security_headers(request, call_next):
    response: Response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Content-Security-Policy"] = CSP
    return response


@app.middleware("http")
async def require_auth(request, call_next):
    """Optional bearer-token auth for production deployments.

    Only validates requests to /api/* routes when CDAILY_API_TOKEN is set.
    The home page (GET /) and static files remain open.
    """
    if _AUTH_TOKEN and request.url.path.startswith("/api/"):
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {_AUTH_TOKEN}"
        if auth != expected:
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "Unauthorized — provide Authorization: Bearer ***"},
            )
    response = await call_next(request)
    return response


@app.middleware("http")
async def check_csrf(request, call_next):
    """Basic CSRF guard for POST/PUT/DELETE endpoints."""
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        current_origin = _request_origin(request)

        if not origin and not referer:
            response = await call_next(request)
            return response

        allowed = False
        if origin:
            if origin in ALLOWED_ORIGINS or origin == current_origin:
                allowed = True

        if not allowed and referer:
            if current_origin and referer.startswith(current_origin):
                allowed = True
            else:
                for ao in ALLOWED_ORIGINS:
                    if referer.startswith(ao):
                        allowed = True
                        break

        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": "Cross-site request forbidden"},
            )

    response = await call_next(request)
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(system_router)
app.include_router(articles_router)
app.include_router(blogs_router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "cdaily.main:app",
        host=CONFIG["host"],
        port=CONFIG["port"],
        reload=False,
    )


if __name__ == "__main__":
    main()

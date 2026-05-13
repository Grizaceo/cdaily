"""CDaily FastAPI application bootstrap."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routes.articles import router as articles_router
from .routes.system import router as system_router

BASE_DIR = Path(__file__).parent

init_db()

app = FastAPI(title="CDaily", description="Cristóbal's Daily Feed")

# CSP: basic defense-in-depth — restricts inline styles/scripts
CSP = (
    "default-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' https:; "
    "script-src 'self'"
)

ALLOWED_ORIGINS = frozenset({
    "http://127.0.0.1:7890",
    "http://localhost:7890",
    # Docker: host.docker.internal from container → host
    "http://host.docker.internal:7890",
})


@app.middleware("http")
async def add_security_headers(request, call_next):
    response: Response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Content-Security-Policy"] = CSP
    return response


@app.middleware("http")
async def check_csrf(request, call_next):
    """Basic CSRF guard for POST/PUT/DELETE endpoints.

    For localhost-only deployments this is defense-in-depth.
    If a browser extension or other page on the same machine makes
    a cross-origin POST, this blocks it unless the Origin matches.
    """
    if request.method in ("POST", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        # If neither Origin nor Referer is sent, allow (local curl, etc.)
        if not origin and not referer:
            response = await call_next(request)
            return response

        # Check Origin first (more reliable, set by modern browsers)
        allowed = False
        if origin:
            if origin in ALLOWED_ORIGINS:
                allowed = True

        # Fall back to Referer if Origin wasn't set
        if not allowed and referer:
            # Referer includes full path — just check the origin part
            for ao in ALLOWED_ORIGINS:
                if referer.startswith(ao):
                    allowed = True
                    break

        if not allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": "Cross-site request forbidden"},
            )

    response = await call_next(request)
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(system_router)
app.include_router(articles_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=7890,
        reload=False,
    )

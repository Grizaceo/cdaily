"""CDaily FastAPI application bootstrap."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routes.articles import router as articles_router
from .routes.system import router as system_router

BASE_DIR = Path(__file__).parent

init_db()

app = FastAPI(title="CDaily", description="Cristóbal's Daily Feed")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(system_router)
app.include_router(articles_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=7890,
        reload=False,
    )

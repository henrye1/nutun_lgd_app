"""FastAPI app. Serves /api/* and, when web/dist exists, the built React front end."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routers import curves as curves_router
from api.routers import db as db_router
from nutun_engine import __version__

app = FastAPI(title="Nutun AC Valuation App", version=__version__)
app.include_router(db_router.router)
app.include_router(curves_router.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        root = DIST.resolve()
        target = (DIST / path).resolve()
        inside = target.is_relative_to(root) and target != root
        return FileResponse(target if path and inside and target.is_file() else DIST / "index.html")

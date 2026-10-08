from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from api.catalog import Catalog, check_objects
from api.db import make_client_engine, ping
from api.deps import get_catalog, get_settings
from api.settings import Settings

router = APIRouter(prefix="/api/db", tags=["db"])


@router.get("/status")
def db_status(settings: Settings = Depends(get_settings)) -> dict:
    base = {
        "configured": settings.client_db_configured(),
        "server": settings.db_server,
        "database": settings.db_name,
        "auth": settings.db_auth,
    }
    if not base["configured"]:
        return {**base, "reachable": False, "error": "NUTUN_DB_SERVER is not set"}
    try:
        ok, err = ping(make_client_engine(settings))
    except Exception as exc:
        ok, err = False, f"{type(exc).__name__}: {str(exc)[:300]}"
    return {**base, "reachable": ok, "error": err}


@router.get("/objects")
def db_objects(catalog: Catalog = Depends(get_catalog)) -> list[dict]:
    return [asdict(s) for s in check_objects(catalog)]

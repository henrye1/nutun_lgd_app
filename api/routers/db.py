from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine

from api.catalog import Catalog, check_objects
from api.db import make_client_engine, ping
from api.deps import get_catalog, get_engine, get_settings
from api.info_query import fetch_info, info_summary
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


@router.get("/info")
def db_info(
    report_month: date = Query(...),
    limit: int = Query(50, ge=0, le=5000),
    in_scope_only: bool = False,
    engine: Engine = Depends(get_engine),
) -> dict:
    try:
        df = fetch_info(engine, report_month, in_scope_only=in_scope_only)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Info query failed: {type(exc).__name__}: {str(exc)[:300]}")
    head = df.head(limit)
    rows = head.astype(object).where(head.notna(), None).to_dict(orient="records")
    for r in rows:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
    return {"summary": info_summary(df), "rows": rows}

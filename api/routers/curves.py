from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from api.db_inputs import load_inputs_from_db
from api.deps import get_engine, get_settings
from api.runs import RUNS
from api.settings import Settings
from nutun_engine.config import PRESETS, FitMode
from nutun_engine.inputs import load_inputs_from_fixtures
from nutun_engine.pipeline import refit_block, run_curves

router = APIRouter(prefix="/api/curves", tags=["curves"])


class RunRequest(BaseModel):
    report_month: date
    preset: Literal["PARITY_JUL26", "CORRECTED"] = "PARITY_JUL26"
    source: Literal["db", "fixtures"] = "db"
    modes: list[Literal["THREE_PARAM", "TWO_PARAM_FIXED_MU"]] = Field(default=["THREE_PARAM", "TWO_PARAM_FIXED_MU"])


class RefitRequest(BaseModel):
    grid: Literal["ROLLING", "VALUATION_CALC"] = "ROLLING"
    k: int = 0
    vb: int
    mode: FitMode
    mu: float | None = None
    m: float | None = None
    s: float | None = None
    cn: float | None = None


def _row(f) -> dict:
    return {kk: (None if isinstance(v, float) and np.isnan(v) else v) for kk, v in f.params_row().items()}


def _counts(run) -> tuple[int, int]:
    allf = list(run.fits.values()) + list(run.calc_fits.values())
    return len(allf), sum(f.status == "NOT_FITTABLE" for f in allf)


def _summary(run, meta: dict) -> dict:
    n_fits, n_nf = _counts(run)
    return {
        "run_id": meta["run_id"], "report_month": meta["report_month"], "preset": meta["preset"],
        "source": meta["source"], "modes": meta.get("modes", []), "cohorts": list(run.cfg.curves.cohorts),
        "n_months": run.cfg.curves.n_months, "ma_window": run.cfg.curves.ma_window,
        "ma_fit_mode": run.cfg.curves.ma_fit_mode,
        "ma_members": {str(vb): ks for vb, ks in run.curve_set.ma_members.items()},
        "bounds_params_from": {str(vb): s for vb, s in run.bounds_params_from.items()},
        "n_fits": n_fits, "n_not_fittable": n_nf, "warnings": list(run.warnings), "timings": run.timings,
        "quirk_flags": run.cfg.quirk_flags(),
    }


def _records(df: pd.DataFrame) -> list[dict]:
    return df.replace({np.nan: None}).to_dict(orient="records")


def _run_or_404(run_id: str):
    hit = RUNS.get(run_id)
    if hit is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return hit


@router.post("/run")
def start_run(req: RunRequest, settings: Settings = Depends(get_settings)) -> dict:
    cfg = PRESETS[req.preset]()
    try:
        if req.source == "fixtures":
            fx = Path(settings.fixtures_dir)
            if not (fx / "manifest.json").exists():
                raise FileNotFoundError(f"fixtures not found under {fx}")
            inputs = load_inputs_from_fixtures(fx)
        else:
            engine = get_engine(settings)
            inputs = load_inputs_from_db(engine, req.report_month, settings.vb_override_csv)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"could not load inputs from {req.source}: {type(exc).__name__}: {str(exc)[:300]}",
        )
    try:
            run = run_curves(inputs, cfg, req.report_month, modes=tuple(req.modes))
    except (ValueError, IndexError, KeyError) as exc:  # a configuration the engine refuses (e.g. ma_missing = FAIL)
        raise HTTPException(status_code=422, detail=f"curve run failed: {type(exc).__name__}: {str(exc)[:300]}")
    n_fits, n_nf = _counts(run)
    meta = {
        "report_month": req.report_month.isoformat(),
        "preset": req.preset,
        "source": req.source,
        "modes": list(req.modes),
        "n_fits": n_fits,
        "n_not_fittable": n_nf,
        "warnings": list(run.warnings),
        "timings": run.timings,
    }
    rid = RUNS.put(run, meta)
    return {"run_id": rid, **meta}


@router.get("/runs")
def list_runs() -> list[dict]:
    return RUNS.list()


@router.get("/{run_id}/summary")
def summary(run_id: str) -> dict:
    run, meta = _run_or_404(run_id)
    return _summary(run, meta)


@router.post("/{run_id}/refit")
def refit(run_id: str, req: RefitRequest) -> dict:
    run, meta = _run_or_404(run_id)
    manual = None
    if req.mode == "MANUAL":
        if req.m is None or req.s is None or req.cn is None:
            raise HTTPException(status_code=422, detail="MANUAL mode needs m, s and cn")
        import math

        if not all(math.isfinite(v) for v in (req.m, req.s, req.cn)) or req.s <= 1e-4 or req.cn <= 1e-9:
            raise HTTPException(status_code=422, detail="MANUAL mode needs finite m, s > 1e-4 and cn > 1e-9")
        manual = (req.m, req.s, req.cn)
    try:
        new = refit_block(run, grid=req.grid, k=req.k, vb=req.vb, mode=req.mode, mu=req.mu, manual=manual)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    n_fits, n_nf = _counts(new)
    meta2 = {**meta, "warnings": list(new.warnings), "timings": new.timings, "n_fits": n_fits, "n_not_fittable": n_nf}
    RUNS.replace(run_id, new, meta2)
    f = new.fits[(req.mode, req.k, req.vb)] if req.grid == "ROLLING" else new.calc_fits[(req.mode, req.vb)]
    return {"fit": _row(f) | {"grid": req.grid}, "summary": _summary(new, meta2)}


@router.get("/{run_id}/params")
def params(run_id: str) -> list[dict]:
    run, _ = _run_or_404(run_id)
    return _records(run.params_frame())


@router.get("/{run_id}/grids")
def grids(run_id: str, rule_set: Literal["ROLLING", "VALUATION_CALC"] = "ROLLING", k: int = 0) -> list[dict]:
    run, _ = _run_or_404(run_id)
    if rule_set == "VALUATION_CALC":
        g = run.grid_calc
    else:
        g = run.grids_rolling[k] if 0 <= k < len(run.grids_rolling) else None
    if g is None:
        raise HTTPException(status_code=404, detail=f"no grid k={k}")
    return _records(g.frame())


@router.get("/{run_id}/curves")
def curves(run_id: str) -> list[dict]:
    run, _ = _run_or_404(run_id)
    return _records(run.curves_frame())


@router.get("/{run_id}/bounds/{vb}")
def bounds(run_id: str, vb: int) -> dict:
    run, _ = _run_or_404(run_id)
    if vb not in run.bounds:
        raise HTTPException(status_code=404, detail=f"no bounds for VB{vb}")
    b = run.bounds[vb]
    return {
        "vb": vb, "k": b.k, "points": b.points, "n_points": b.n_points, "p": b.p, "df": b.df, "sse": b.sse,
        "s_e": b.s_e, "t_mult": b.t_mult, "V": b.V.tolist(), "W": b.W.tolist(), "P": b.P.tolist(), "Q": b.Q.tolist(),
        "table": _records(run.bounds_table(vb)), "warnings": list(b.warnings),
        "sensitivity": run.bounds_sensitivity.get(vb, {}), "params_from": run.bounds_params_from.get(vb, ""),
    }


@router.get("/{run_id}/fit/{mode}/{k}/{vb}")
def fit(run_id: str, mode: FitMode, k: int, vb: int, grid: Literal["ROLLING", "VALUATION_CALC"] = "ROLLING") -> dict:
    run, _ = _run_or_404(run_id)
    f = run.fits.get((mode, k, vb)) if grid == "ROLLING" else run.calc_fits.get((mode, vb))
    if f is None:
        raise HTTPException(status_code=404, detail=f"no fit {mode} k={k} VB{vb} on {grid}")
    return _row(f) | {"grid": grid}


@router.get("/{run_id}/paste-block.csv")
def paste_block(run_id: str) -> PlainTextResponse:
    run, _ = _run_or_404(run_id)
    return PlainTextResponse(run.curve_set.paste_block().to_csv(index=False), media_type="text/csv")

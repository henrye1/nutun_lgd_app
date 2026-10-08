"""Curve run orchestration (spec §7.1 stages prepare → grids → fit → bounds → curves)."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from nutun_engine.bounds import BoundsResult, prediction_limits
from nutun_engine.config import RunConfig
from nutun_engine.curves import CurveSet, assemble_curve_set
from nutun_engine.fit import FitResult, fit_block, fit_grid
from nutun_engine.grids import YieldGrid, build_rolling_grids, build_valuation_calc_grid
from nutun_engine.inputs import RunInputs
from nutun_engine.prepare import prepare_rolling, prepare_valuation_calc

Progress = Callable[[str, int | None, int | None], None]


def prepare_grids(inputs: RunInputs, cfg: RunConfig, report_month: date):
    prep = prepare_valuation_calc(inputs, cfg, report_month)
    rp = prepare_rolling(inputs, cfg, report_month)
    return prep, rp, build_valuation_calc_grid(prep, cfg, report_month), build_rolling_grids(rp, cfg, report_month)


@dataclass(frozen=True)
class CurveRun:
    report_month: date
    cfg: RunConfig
    grid_calc: YieldGrid
    grids_rolling: list[YieldGrid]
    fits: dict[tuple[str, int, int], FitResult]
    calc_fits: dict[tuple[str, int], FitResult]  # (mode, vb): fits of the VALUATION_CALC grid
    bounds: dict[int, BoundsResult]
    curve_set: CurveSet
    warnings: tuple[str, ...] = field(default_factory=tuple)
    timings: dict[str, float] = field(default_factory=dict)

    def params_frame(self) -> pd.DataFrame:
        rows = [f.params_row() | {"grid": "ROLLING"} for f in self.fits.values()]
        rows += [f.params_row() | {"grid": "VALUATION_CALC"} for f in self.calc_fits.values()]
        return pd.DataFrame(rows)

    def grids_frame(self) -> pd.DataFrame:
        return pd.concat([self.grid_calc.frame()] + [g.frame() for g in self.grids_rolling], ignore_index=True)

    def curves_frame(self) -> pd.DataFrame:
        return self.curve_set.frame()

    def bounds_table(self, vb: int) -> pd.DataFrame:
        b = self.bounds[vb]
        return pd.DataFrame(
            {
                "t": b.t.astype(int),
                "obs": np.where(b.used, b.pred + b.resid, 0.0),
                "keep": b.used,
                "used": b.used.astype(int),
                "w": b.w, "z": b.z, "phi": b.phi, "pred": b.pred, "resid": b.resid,
                "x_m": b.x_m, "x_s": b.x_s, "x_cn": b.x_cn, "h3": b.h3, "h2": b.h2, "h": b.h,
                "sqrt_term": b.sqrt_term, "se_i": b.se_i, "half": b.half, "lower": b.lower, "upper": b.upper,
            }
        )


def run_curves(
    inputs: RunInputs,
    cfg: RunConfig,
    report_month: date | None = None,
    *,
    modes=("THREE_PARAM", "TWO_PARAM_FIXED_MU"),
    warm=None,
    uploaded: pd.DataFrame | None = None,
    progress: Progress | None = None,
) -> CurveRun:
    D = report_month or cfg.run.report_month
    notify = progress or (lambda *_: None)
    timings: dict[str, float] = {}
    warnings: list[str] = []
    t0 = time.perf_counter()

    notify("prepare", None, None)
    t1 = time.perf_counter()
    prep, rp, grid_calc, grids = prepare_grids(inputs, cfg, D)
    warnings += prep.warnings + rp.warnings
    timings["prepare"] = time.perf_counter() - t1
    notify("grids", None, None)
    timings["grids"] = 0.0

    t1 = time.perf_counter()
    fits: dict[tuple[str, int, int], FitResult] = {}
    mu = cfg.fixed_mu_lookup()
    for mode in modes:
        for g in grids:
            notify("fit", g.k, None)
            for r in fit_grid(g, cfg, mode, mu, warm=warm):
                fits[(mode, g.k, r.vb)] = r
                if r.status == "NOT_FITTABLE":
                    warnings.append(f"{mode} VB{r.vb} k={r.k}: not fittable ({r.reason})")
                elif r.warn:
                    warnings.append(f"{mode} VB{r.vb} k={r.k}: Warn = CHECK")
    calc_fits: dict[tuple[str, int], FitResult] = {}
    for mode in modes:
        if mode == "TWO_PARAM_FIXED_MU":
            continue  # the fixed-mu table is keyed by rolling month k
        for r in fit_grid(grid_calc, cfg, mode, {}, warm=warm):
            calc_fits[(mode, r.vb)] = r
            if r.status == "NOT_FITTABLE":
                warnings.append(f"{mode} VALUATION_CALC VB{r.vb}: not fittable ({r.reason})")
    timings["fit"] = time.perf_counter() - t1

    t1 = time.perf_counter()
    notify("bounds", None, None)
    data_grid = grid_calc if cfg.bounds.data_rule_set == "VALUATION_CALC" else grids[cfg.bounds.data_k]
    mt = cfg.bounds.matrix_t_max or {}
    qt = cfg.bounds.sse_t_max or {}
    bounds: dict[int, BoundsResult] = {}
    for vb in cfg.curves.cohorts:
        f, where = _bound_params(cfg, vb, fits, calc_fits, grid_calc)
        if f is None or f.status == "NOT_FITTABLE":
            warnings.append(f"VB{vb}: no usable bound parameters ({where}); bound curves blank")
            continue
        c = data_grid.column(vb)
        b = prediction_limits(
            data_grid.t, data_grid.constrained[:, c], data_grid.keep[:, c], f.m, f.s, f.cn,
            alpha=cfg.curves.alpha, p=f.p, points=cfg.bounds.points, k=data_grid.k,
            report_month=data_grid.report_month, vb=vb, matrix_t_max=mt.get(vb), sse_t_max=qt.get(vb),
        )
        warnings += list(b.warnings)
        bounds[vb] = b
    timings["bounds"] = time.perf_counter() - t1

    t1 = time.perf_counter()
    notify("curves", None, None)
    cs = assemble_curve_set(cfg, D, fits, bounds, uploaded=uploaded)
    warnings += list(cs.warnings)
    timings["curves"] = time.perf_counter() - t1
    timings["total"] = time.perf_counter() - t0
    return CurveRun(D, cfg, grid_calc, grids, fits, calc_fits, bounds, cs, tuple(warnings), timings)


def _bound_params(cfg: RunConfig, vb: int, fits, calc_fits, grid_calc):
    """The (fit, description) that parameterises the prediction limits of VB, per cfg.bounds."""
    mode = cfg.bounds.params_fit_mode
    ov = cfg.bounds.params_vb_override.get(vb)
    if ov is not None:
        rule_set, k = ov
        if rule_set == "ROLLING":
            return fits.get((mode, k, vb)), f"override ROLLING {mode} k={k}"
        return calc_fits.get((mode, vb)), f"override VALUATION_CALC {mode}"
    src = cfg.bounds.params_source
    if src == "MANUAL":
        prm = (cfg.bounds.manual_params or {}).get(vb)
        if prm is None:
            return None, "MANUAL params missing"
        c = grid_calc.column(vb)
        return fit_block(grid_calc.t, grid_calc.constrained[:, c], grid_calc.keep[:, c], k=0,
                         report_month=grid_calc.report_month, vb=vb, mode="MANUAL", cfg=cfg, manual=prm), "MANUAL"
    if src == "VALUATION_CALC_FIT":
        return calc_fits.get((mode, vb)), f"VALUATION_CALC {mode}"
    return fits.get((mode, cfg.bounds.params_k, vb)), f"ROLLING {mode} k={cfg.bounds.params_k}"

"""Curve set assembly (spec §7.6): per-k curves, the moving average, extension to t_max, bound curves."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from nutun_engine.bounds import BoundsResult
from nutun_engine.config import RunConfig
from nutun_engine.fit import FitResult
from nutun_engine.lognormal import curve

USABLE = ("OK", "MANUAL")


def curve_values(fit: FitResult, t: np.ndarray) -> np.ndarray:
    if fit.status not in USABLE:
        return np.full(len(t), np.nan)
    return curve(np.asarray(t, float), fit.m, fit.s, fit.cn)


def ma_curve(fits: list[FitResult], t, missing: Literal["SKIP_AND_WARN", "FAIL"]):
    """Mean of the curve VALUES over the usable fits (never of the parameters) — Curves_MA6!B6."""
    t = np.asarray(t, float)
    rows, ks, warnings = [], [], []
    for f in fits:
        if f.status in USABLE:
            rows.append(curve_values(f, t))
            ks.append(f.k)
        else:
            msg = f"VB{f.vb} k={f.k}: not fittable ({f.reason}); skipped in the moving average"
            if missing == "FAIL":
                raise ValueError(msg)
            warnings.append(msg)
    if not rows:
        warnings.append(f"no usable fit for the moving average ({len(fits)} blocks)")
        return np.full(len(t), np.nan), [], warnings
    return np.mean(np.vstack(rows), axis=0), ks, warnings


def bound_curves(b: BoundsResult | None, t_max: int) -> tuple[np.ndarray, np.ndarray]:
    lb, ub = np.full(t_max, np.nan), np.full(t_max, np.nan)
    if b is None:
        return lb, ub
    idx = b.t.astype(int) - 1
    inside = (idx >= 0) & (idx < t_max)
    lb[idx[inside]] = b.lower[inside]
    ub[idx[inside]] = b.upper[inside]
    return lb, ub


@dataclass(frozen=True)
class CurveSet:
    report_month: date
    cohorts: tuple[int, ...]
    t: np.ndarray
    C: np.ndarray
    LB: np.ndarray
    UB: np.ndarray
    source: str
    ma_members: dict[int, list[int]]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def column(self, vb: int) -> int:
        return self.cohorts.index(vb)

    def frame(self) -> pd.DataFrame:
        T, V = self.C.shape
        return pd.DataFrame(
            {
                "vb": np.tile(np.array(self.cohorts), T),
                "t": np.repeat(self.t, V),
                "curve": self.C.ravel(),
                "lb": self.LB.ravel(),
                "ub": self.UB.ravel(),
            }
        )

    def paste_block(self) -> pd.DataFrame:
        """The Curves!A3:S503 layout: t, curve per VB, UB per VB, LB per VB."""
        cols = {"t": self.t.astype(int)}
        for i, vb in enumerate(self.cohorts):
            cols[str(vb)] = self.C[:, i]
        for i, vb in enumerate(self.cohorts):
            cols[f"UB {vb}"] = self.UB[:, i]
        for i, vb in enumerate(self.cohorts):
            cols[f"LB {vb}"] = self.LB[:, i]
        return pd.DataFrame(cols)


def assemble_curve_set(cfg: RunConfig, report_month: date, fits, bounds, uploaded: pd.DataFrame | None = None) -> CurveSet:
    cohorts = tuple(cfg.curves.cohorts)
    t_max = cfg.curves.t_max
    t = np.arange(1.0, t_max + 1.0)
    C = np.full((t_max, len(cohorts)), np.nan)
    LB, UB = np.full_like(C, np.nan), np.full_like(C, np.nan)
    warnings: list[str] = []
    members: dict[int, list[int]] = {}
    src = cfg.curves.valuation_source
    if src == "UPLOADED":
        if uploaded is None:
            raise ValueError("curves.valuation_source = UPLOADED but no uploaded curve table was given")
        up = uploaded.set_index("t").reindex(range(1, t_max + 1))
        for i, vb in enumerate(cohorts):
            C[:, i] = up[str(vb)].to_numpy(dtype=float)
            for arr, key in ((LB, f"lb_{vb}"), (UB, f"ub_{vb}")):
                if key in up.columns:
                    arr[:, i] = up[key].to_numpy(dtype=float)
            members[vb] = []
        if np.isnan(C).any():
            warnings.append("uploaded curve has blanks inside 1..t_max")
    else:
        mode = cfg.curves.ma_fit_mode
        ks = list(range(cfg.curves.ma_window)) if src == "MA_OF_FITS" else [0]
        for i, vb in enumerate(cohorts):
            fl = []
            for k in ks:
                f = fits.get((mode, k, vb))
                if f is None:
                    warnings.append(f"VB{vb} k={k}: no {mode} fit available for the moving average")
                else:
                    fl.append(f)
            if fl:
                vals, used_ks, w = ma_curve(fl, t, cfg.curves.ma_missing)
            else:
                vals, used_ks, w = np.full(t_max, np.nan), [], [f"VB{vb}: no fits for the curve"]
            C[:, i] = vals
            members[vb] = used_ks
            warnings.extend(w)
    for i, vb in enumerate(cohorts):
        lb, ub = bound_curves(bounds.get(vb), t_max)
        LB[:, i], UB[:, i] = lb, ub
    if cfg.bounds.q12_vb15_blank_from_vb11 and 11 in cohorts and 15 in cohorts:  # Curves!I5:I503 tests Cohort_11
        i11, i15 = cohorts.index(11), cohorts.index(15)
        UB[1:, i15] = np.where(UB[1:, i11] == 0, np.nan, UB[1:, i15])
    return CurveSet(report_month, cohorts, t, C, LB, UB, src, members, tuple(warnings))

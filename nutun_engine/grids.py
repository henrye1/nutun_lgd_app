"""Yield grids by cohort × month-on-book (spec §7.3): Yields_Mk and ACM_Payments_Calc!W:BM."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from nutun_engine.config import RunConfig
from nutun_engine.dates import edate
from nutun_engine.prepare import PrepResult, RollingPrep


@dataclass(frozen=True)
class YieldGrid:
    rule_set: str
    k: int
    report_month: date
    cohorts: tuple[int, ...]
    t: np.ndarray  # [T] = 1..T
    sum_pay: np.ndarray  # [T, V]  Σ FLI-adjusted payments
    sum_bal: np.ndarray  # [T, V]  Σ Face
    n_ho: np.ndarray  # [T, V]  rows (books paying at t)
    yield_: np.ndarray  # [T, V]  sum_pay / sum_bal, NaN when sum_bal = 0
    keep: np.ndarray  # [T, V]  bool
    constrained: np.ndarray  # [T, V]  yield if kept else 0
    n_kept: np.ndarray  # [V]     K
    contiguous: np.ndarray  # [V]     kept points are exactly 1..K

    def column(self, vb: int) -> int:
        return self.cohorts.index(vb)

    def frame(self) -> pd.DataFrame:
        T, V = self.sum_pay.shape
        tt = np.repeat(self.t, V)
        vb = np.tile(np.array(self.cohorts), T)
        return pd.DataFrame(
            {
                "rule_set": self.rule_set,
                "k": self.k,
                "report_month": self.report_month,
                "vb": vb,
                "t": tt,
                "sum_pay": self.sum_pay.ravel(),
                "sum_bal": self.sum_bal.ravel(),
                "n_ho": self.n_ho.ravel(),
                "yield": self.yield_.ravel(),
                "keep": self.keep.ravel(),
                "constrained": self.constrained.ravel(),
            }
        )


def aggregate_grid(rows: pd.DataFrame, cfg: RunConfig, rule_set: str, k: int, report_month: date) -> YieldGrid:
    cohorts = tuple(cfg.curves.cohorts)
    T = cfg.curves.t_grid
    bal_col = "Face" if "Face" in rows.columns else "balance"
    sub = rows.loc[rows.Count.between(1, T) & rows.VB.isin(cohorts), ["VB", "Count", "FLIadj", bal_col]]
    vb_idx = sub.VB.map({vb: i for i, vb in enumerate(cohorts)}).to_numpy(dtype="int64")
    t_idx = sub.Count.to_numpy(dtype="int64") - 1
    shape = (T, len(cohorts))
    sum_pay = np.zeros(shape)
    np.add.at(sum_pay, (t_idx, vb_idx), np.nan_to_num(sub.FLIadj.to_numpy(dtype="float64"), nan=0.0))  # SUMIFS skips blanks
    sum_bal = np.zeros(shape)
    np.add.at(sum_bal, (t_idx, vb_idx), sub[bal_col].to_numpy(dtype="float64"))
    n_ho = np.zeros(shape, dtype="int64")
    np.add.at(n_ho, (t_idx, vb_idx), 1)  # COUNTIFS counts every row

    with np.errstate(divide="ignore", invalid="ignore"):
        yield_ = np.where(sum_bal != 0, sum_pay / np.where(sum_bal != 0, sum_bal, 1.0), np.nan)
    t = np.arange(1, T + 1)
    within = t <= cfg.curves.ndata
    max_bal = np.where(within[:, None], sum_bal, 0.0).max(axis=0)  # MAXIFS over t ≤ ndata
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(max_bal > 0, sum_bal / np.where(max_bal > 0, max_bal, 1.0), 0.0)  # IFERROR(…, 0)
    keep = within[:, None] & (n_ho >= cfg.curves.min_nho) & (ratio >= cfg.curves.min_bal_ratio)
    constrained = np.where(keep, np.nan_to_num(yield_, nan=0.0), 0.0)
    n_kept = keep.sum(axis=0)
    contiguous = np.array([bool(keep[:K, v].all()) if K > 0 else False for v, K in enumerate(n_kept)])
    return YieldGrid(
        rule_set, k, report_month, cohorts, t, sum_pay, sum_bal, n_ho, yield_, keep, constrained, n_kept, contiguous
    )


def build_valuation_calc_grid(prep: PrepResult, cfg: RunConfig, report_month: date) -> YieldGrid:
    rows = prep.rows.loc[prep.rows.Include]
    return aggregate_grid(rows, cfg, "VALUATION_CALC", 0, edate(report_month, cfg.curves.calc_offset))


def build_rolling_grids(rp: RollingPrep, cfg: RunConfig, report_month: date) -> list[YieldGrid]:
    p = rp.payments
    out = []
    for k in range(cfg.curves.n_months):
        rows = p.loc[(p.kmin <= k) & (p.kmax >= k)]
        out.append(aggregate_grid(rows, cfg, "ROLLING", k, edate(report_month, -k)))
    return out

"""Levenberg–Marquardt fit of the log-normal curve: a port of modRollingFitLM / modRollingFitLMFixed (spec §7.4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

from nutun_engine.config import FitMode, RunConfig
from nutun_engine.grids import YieldGrid
from nutun_engine.lognormal import curve, jacobian, weighted_sse

FitStatus = Literal["OK", "NOT_FITTABLE", "MANUAL"]
S_MIN, CN_MIN = 1e-4, 1e-9
LAM0, LAM_MIN, REL_GAIN_STOP = 1e-3, 1e-12, 1e-15
DEFAULT_START = (4.0, 1.7, 0.3)


@dataclass(frozen=True)
class LMOutcome:
    m: float
    s: float
    cn: float
    sse: float
    iterations: int
    accepted_steps: int


def solve3(B: np.ndarray, rhs: np.ndarray) -> np.ndarray | None:
    """Gaussian elimination with partial pivoting on a 3×3 system; None if a pivot is below 1e-300 (VBA Solve3)."""
    M = np.column_stack([B.astype(float), rhs.astype(float)])
    for c in range(3):
        piv = c + int(np.argmax(np.abs(M[c:, c])))
        if abs(M[piv, c]) < 1e-300:
            return None
        if piv != c:
            M[[c, piv]] = M[[piv, c]]
        for r in range(c + 1, 3):
            fct = M[r, c] / M[c, c]
            M[r, c:] -= fct * M[c, c:]
    x = np.zeros(3)
    for r in (2, 1, 0):
        x[r] = (M[r, 3] - np.dot(M[r, r + 1 : 3], x[r + 1 : 3])) / M[r, r]
    return x


def _normal_equations(t, y, w, m, s, cn):
    f, z, phi, x_m, x_s, x_cn = jacobian(t, m, s, cn)
    r = y - f
    J = np.column_stack([x_m, x_s, x_cn])
    A = (J * w[:, None]).T @ J
    g = J.T @ (w * r)
    return A, g, float(np.sum(w * r * r))


def lm_run(t, y, w, m, s, cn, mbound, fix_mu=False, max_iter=500, max_tries=30) -> LMOutcome:
    if m > mbound and not fix_mu:
        m = mbound
    lam = LAM0
    accepted = 0
    it = 0
    for it in range(1, max_iter + 1):
        A, g, sse = _normal_equations(t, y, w, m, s, cn)
        at_bound = fix_mu or (m >= mbound - 1e-12 and g[0] > 0)
        step_ok = False
        rel_gain = 0.0
        for _ in range(max_tries):
            B = A.copy()
            B[np.diag_indices(3)] = np.diag(A) * (1.0 + lam) + 1e-300
            gg = g.copy()
            if at_bound:
                B[0, :] = 0.0
                B[:, 0] = 0.0
                B[0, 0] = 1.0
                gg[0] = 0.0
            d = solve3(B, gg)
            if d is not None:
                m2 = m + d[0]
                if m2 > mbound and not fix_mu:
                    m2 = mbound
                s2, c2 = s + d[1], cn + d[2]
                if s2 > S_MIN and c2 > CN_MIN:
                    sse2 = weighted_sse(t, y, w, m2, s2, c2)
                    if sse2 < sse:
                        rel_gain = (sse - sse2) / sse if sse > 0 else 0.0
                        m, s, cn = m2, s2, c2
                        lam = max(lam / 10.0, LAM_MIN)
                        step_ok = True
                        accepted += 1
                        break
            lam *= 10.0
        if not step_ok or rel_gain < REL_GAIN_STOP:
            break
    return LMOutcome(m, s, cn, weighted_sse(t, y, w, m, s, cn), it, accepted)


@dataclass(frozen=True)
class FitResult:
    k: int
    report_month: date
    vb: int
    mode: str
    status: FitStatus
    reason: str
    m: float
    s: float
    cn: float
    mbound: float
    m_at_bound: int
    K: int
    contiguous: bool
    sum_count: int
    sse: float
    p: int
    df: int
    s_e: float
    mode_t: float
    lifetime: float
    rule4: str
    warn: str
    iterations: int
    start_used: int
    mu_source: str

    def params_row(self) -> dict:
        return {
            "k": self.k,
            "Report month": self.report_month.strftime("%Y-%m"),
            "vb": self.vb,
            "m": self.m,
            "s": self.s,
            "cn": self.cn,
            "mbound": self.mbound,
            "m_at_bound": self.m_at_bound,
            "K (fit points)": self.K,
            "contiguous?": "YES" if self.contiguous else ("n/a" if self.K == 0 else "NO"),
            "Sum count": self.sum_count,
            "Weighted SSE": self.sse,
            "p": self.p,
            "df": self.df,
            "s_e": self.s_e,
            "Mode": self.mode_t,
            "Lifetime": self.lifetime,
            "Rule 4": self.rule4,
            "Warn": self.warn,
            "mode": self.mode,
            "status": self.status,
            "reason": self.reason,
            "iterations": self.iterations,
            "start_used": self.start_used,
            "mu_source": self.mu_source,
        }


def _used_points(t, y, keep):
    used = keep & (t > 0)
    return t[used].astype(float), y[used].astype(float), used


def diagnostics(t, y, keep, m, s, cn, mbound, cfg: RunConfig, mode: str) -> dict:
    tt, yy, used = _used_points(t, y, keep)
    K = int(used.sum())
    contiguous = bool(keep[:K].all()) if K > 0 else False
    sum_count = int(tt.sum())
    w = tt / sum_count if sum_count else tt
    sse = weighted_sse(tt, yy, w, m, s, cn) if K else float("nan")
    m_at_bound = int(abs(m - mbound) < 1e-4)
    if cfg.bounds.p_rule == "FIXED_MU_IS_2" and mode == "TWO_PARAM_FIXED_MU":
        p = 2
    else:
        p = 2 if abs(m - mbound) < 1e-6 else 3
    df = K - p
    s_e = float(np.sqrt(sse / df)) if df > 0 else float("nan")
    lifetime = float(curve(np.arange(1.0, cfg.fit.lifetime_horizon + 1.0), m, s, cn).sum())
    rule4 = "OK" if K >= cfg.curves.min_fit_points else "THIN"
    warn = "CHECK" if (m_at_bound == 1 or K < cfg.curves.min_fit_points or not contiguous or m > 10) else ""
    return dict(
        K=K, contiguous=contiguous, sum_count=sum_count, sse=sse, p=p, df=df, s_e=s_e,
        mode_t=float(np.exp(m - s * s)), lifetime=lifetime, rule4=rule4, warn=warn, m_at_bound=m_at_bound,
    )


def _not_fittable(k, report_month, vb, mode, reason, mbound, t, keep) -> FitResult:
    K = int((keep & (t > 0)).sum())
    nan = float("nan")
    return FitResult(
        k, report_month, vb, mode, "NOT_FITTABLE", reason, nan, nan, nan, mbound, 0, K,
        bool(keep[:K].all()) if K else False, int(t[keep].sum()), nan, 3, K - 3, nan, nan, nan,
        "THIN" if K < 12 else "OK", "CHECK", 0, -1, "",
    )


def fit_block(t, y, keep, *, k, report_month, vb, mode: FitMode, cfg: RunConfig, mu=None, manual=None, warm=None) -> FitResult:
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    keep = np.asarray(keep, bool)
    mbound = float(cfg.curves.mbound.get(vb, float("nan")))
    if np.isnan(mbound):
        return _not_fittable(k, report_month, vb, mode, "no mbound for this VB", mbound, t, keep)
    if mode == "MANUAL":
        if manual is None:
            return _not_fittable(k, report_month, vb, mode, "MANUAL mode needs (m, s, cn)", mbound, t, keep)
        m, s, cn = (float(v) for v in manual)
        d = diagnostics(t, y, keep, m, s, cn, mbound, cfg, mode)
        return FitResult(
            k, report_month, vb, mode, "MANUAL", "", m, s, cn, mbound, d["m_at_bound"], d["K"], d["contiguous"],
            d["sum_count"], d["sse"], d["p"], d["df"], d["s_e"], d["mode_t"], d["lifetime"], d["rule4"], d["warn"],
            0, -1, "MANUAL",
        )
    tt, yy, used = _used_points(t, y, keep)
    if len(tt) < 4:
        return _not_fittable(k, report_month, vb, mode, f"only {len(tt)} kept points (needs 4)", mbound, t, keep)
    fix_mu = mode == "TWO_PARAM_FIXED_MU"
    if fix_mu and mu is None:
        return _not_fittable(k, report_month, vb, mode, "no fixed μ for this (k, VB)", mbound, t, keep)
    w = tt / tt.sum()
    cur_m, cur_s, cur_cn = warm if warm is not None else DEFAULT_START
    if fix_mu:
        cur_m = float(mu)
    elif cur_m > mbound:
        cur_m = mbound
    if cur_s <= S_MIN:
        cur_s = 1.7
    if cur_cn <= CN_MIN:
        cur_cn = 0.3
    starts = [(cur_m, cur_s, cur_cn)] + [tuple(x) for x in cfg.fit.starts]
    best_i = -1
    best_sse = weighted_sse(tt, yy, w, cur_m, cur_s, cur_cn)
    best_params = (cur_m, cur_s, cur_cn)
    iterations = 0
    for i, (m0, s0, c0) in enumerate(starts):
        m0 = float(mu) if fix_mu else min(m0, mbound)
        out = lm_run(tt, yy, w, m0, s0, c0, mbound, fix_mu=fix_mu)
        iterations += out.iterations
        if out.sse < best_sse:
            best_sse, best_params, best_i = out.sse, (out.m, out.s, out.cn), i
    m, s, cn = best_params
    d = diagnostics(t, y, keep, m, s, cn, mbound, cfg, mode)
    return FitResult(
        k, report_month, vb, mode, "OK", "", m, s, cn, mbound, d["m_at_bound"], d["K"], d["contiguous"],
        d["sum_count"], d["sse"], d["p"], d["df"], d["s_e"], d["mode_t"], d["lifetime"], d["rule4"], d["warn"],
        iterations, best_i, "FIXED_MU_TABLE" if fix_mu else "",
    )


def fit_grid(grid: YieldGrid, cfg: RunConfig, mode: FitMode, mu_lookup, warm=None, manual=None,
             keep_t_max: dict[int, int] | None = None) -> list[FitResult]:
    """`keep_t_max[vb]` (Q22) drops kept points with t > that from the fit, as the valuation Cohort sheets'
    hard-coded SSE ranges do (Cohort_44!B12 sums t <= 48 of 49 kept points)."""
    out = []
    for vb in grid.cohorts:
        c = grid.column(vb)
        key = (grid.k, vb)
        keep = grid.keep[:, c]
        if keep_t_max and keep_t_max.get(vb) is not None:
            keep = keep & (grid.t <= keep_t_max[vb])
        out.append(
            fit_block(
                grid.t, grid.constrained[:, c], keep, k=grid.k, report_month=grid.report_month, vb=vb,
                mode=mode, cfg=cfg, mu=(mu_lookup or {}).get(key), manual=(manual or {}).get(key),
                warm=(warm or {}).get(key),
            )
        )
    return out

"""Prediction limits of the fitted curve (spec §7.5): the Cohort sheets' J:T / V:W blocks and AA:AB columns."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
from scipy.stats import t as student_t

from nutun_engine.lognormal import jacobian, weighted_sse

Points = Literal["KEPT", "CONTIGUOUS_PREFIX"]


def used_mask(t, obs, keep, points: Points) -> np.ndarray:
    t = np.asarray(t, float)
    if points == "KEPT":
        return np.asarray(keep, bool) & (t > 0)
    obs = np.asarray(obs, float)
    numeric = ~np.isnan(obs)
    zero = numeric & (obs == 0)
    n = int(np.argmax(zero)) if zero.any() else int(numeric.sum())  # MATCH(0, obs, 0) − 1, else COUNT(obs)
    return t <= n


def cofactor_inverse3(V: np.ndarray) -> tuple[np.ndarray, float]:
    v11, v12, v13 = V[0, 0], V[0, 1], V[0, 2]
    v22, v23, v33 = V[1, 1], V[1, 2], V[2, 2]
    det = v11 * (v22 * v33 - v23**2) - v12 * (v12 * v33 - v23 * v13) + v13 * (v12 * v23 - v22 * v13)
    if det == 0:
        return np.full((3, 3), np.nan), 0.0
    w11 = (v22 * v33 - v23**2) / det
    w12 = (v13 * v23 - v12 * v33) / det
    w13 = (v12 * v23 - v13 * v22) / det
    w22 = (v11 * v33 - v13**2) / det
    w23 = (v12 * v13 - v11 * v23) / det
    w33 = (v11 * v22 - v12**2) / det
    return np.array([[w11, w12, w13], [w12, w22, w23], [w13, w23, w33]]), float(det)


@dataclass(frozen=True)
class BoundsResult:
    k: int
    report_month: date
    vb: int
    points: str
    n_points: int
    sum_count: int
    p: int
    df: int
    sse: float
    s_e: float
    t_mult: float
    alpha: float
    t: np.ndarray
    used: np.ndarray
    w: np.ndarray
    z: np.ndarray
    phi: np.ndarray
    pred: np.ndarray
    resid: np.ndarray
    x_m: np.ndarray
    x_s: np.ndarray
    x_cn: np.ndarray
    h3: np.ndarray
    h2: np.ndarray
    h: np.ndarray
    sqrt_term: np.ndarray
    se_i: np.ndarray
    half: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    V: np.ndarray
    det_v: float
    W: np.ndarray
    P: np.ndarray
    det_p: float
    Q: np.ndarray
    warnings: tuple[str, ...] = field(default_factory=tuple)


def prediction_limits(t, obs, keep, m, s, cn, *, alpha, p, points: Points, k=0, report_month, vb,
                      matrix_t_max: int | None = None, sse_t_max: int | None = None) -> BoundsResult:
    """`matrix_t_max` (Q22): the valuation Cohort sheets sum X'WX and P over hard-coded row ranges that can
    end before the last used point; when given, only rows with t <= matrix_t_max enter V and P."""
    t = np.asarray(t, float)
    obs = np.asarray(obs, float)
    used = used_mask(t, obs, keep, points)
    n = int(used.sum())
    sum_count = int(t[used].sum())
    warnings: list[str] = []
    w = np.where(used, t / sum_count if sum_count else 0.0, 0.0)
    f, z, phi, xm, xs, xc = jacobian(t, m, s, cn)
    y = np.where(used, np.nan_to_num(obs, nan=0.0), 0.0)
    resid = np.where(used, y - f, 0.0)
    x_m, x_s, x_cn = (np.where(used, v, 0.0) for v in (xm, xs, xc))
    srow = used if sse_t_max is None else (used & (t <= sse_t_max))
    sse = float(np.sum(np.where(srow, w * resid * resid, 0.0)))  # Cohort!B12 (Q22: hard-coded range)
    J = np.column_stack([x_m, x_s, x_cn])
    mrow = used if matrix_t_max is None else (used & (t <= matrix_t_max))
    Jm = np.where(mrow[:, None], J, 0.0)
    V = (Jm * w[:, None]).T @ Jm
    W, det_v = cofactor_inverse3(V)
    P = np.array([[V[1, 1], V[1, 2]], [V[1, 2], V[2, 2]]])
    det_p = float(P[0, 0] * P[1, 1] - P[0, 1] ** 2)
    Q = (np.array([[P[1, 1], -P[0, 1]], [-P[0, 1], P[0, 0]]]) / det_p) if det_p != 0 else np.full((2, 2), np.nan)
    df = n - p
    if n == 0:
        warnings.append(f"VB{vb} k={k}: no usable points for the prediction limits")
    if df <= 0:
        warnings.append(f"VB{vb} k={k}: df = {df} ≤ 0, prediction limits are blank")
    s_e = float(np.sqrt(sse / df)) if df > 0 else float("nan")
    t_mult = float(student_t.ppf(1 - alpha / 2, df)) if df > 0 else float("nan")
    if np.isnan(W).any():
        h3 = np.zeros_like(t)
        if n:
            warnings.append(f"VB{vb} k={k}: singular X'WX")
    else:
        h3 = (
            x_m**2 * W[0, 0] + x_s**2 * W[1, 1] + x_cn**2 * W[2, 2]
            + 2 * x_m * x_s * W[0, 1] + 2 * x_m * x_cn * W[0, 2] + 2 * x_s * x_cn * W[1, 2]
        )
    if np.isnan(Q).any():
        h2 = np.zeros_like(t)
    else:
        h2 = x_s**2 * Q[0, 0] + 2 * x_s * x_cn * Q[0, 1] + x_cn**2 * Q[1, 1]
    h = h3 if p == 3 else h2
    safe_w = np.where(used, w, 1.0)
    sqrt_term = np.where(used, np.sqrt(np.where(used, 1.0 / safe_w + h, 0.0)), 0.0)
    if df > 0:
        se_i = np.where(used, s_e * sqrt_term, 0.0)
        half = np.where(used, t_mult * se_i, 0.0)
    else:
        se_i = np.where(used, np.nan, 0.0)
        half = np.where(used, np.nan, 0.0)
    lower = np.where(used, f - half, np.nan)
    upper = np.where(used, f + half, np.nan)
    return BoundsResult(
        k, report_month, vb, points, n, sum_count, p, df, sse, s_e, t_mult, alpha, t, used, w,
        z, phi, f, resid, x_m, x_s, x_cn, h3, h2, h, sqrt_term, se_i,  # z, phi, pred ungated (rolling layout)
        half, lower, upper, V, det_v, W, P, det_p, Q, tuple(warnings),
    )


def sensitivity(t, obs, keep, m, s, cn, points: Points, t_max: int | None = None) -> dict[str, float]:
    """SSE at each parameter ±1% (Cohort!J4:J9). Weights are t/Σcount over all used points; `t_max` (Q22)
    truncates the summed rows as the valuation sheets' hard-coded ranges do."""
    t = np.asarray(t, float)
    obs = np.asarray(obs, float)
    used = used_mask(t, obs, keep, points)
    sum_count = t[used].sum()
    rows = used if t_max is None else (used & (t <= t_max))
    tt, yy = t[rows], np.nan_to_num(obs[rows], nan=0.0)
    w = tt / sum_count if sum_count else tt
    return {
        "m-1%": weighted_sse(tt, yy, w, m * 0.99, s, cn),
        "m+1%": weighted_sse(tt, yy, w, m * 1.01, s, cn),
        "s-1%": weighted_sse(tt, yy, w, m, s * 0.99, cn),
        "s+1%": weighted_sse(tt, yy, w, m, s * 1.01, cn),
        "cn-1%": weighted_sse(tt, yy, w, m, s, cn * 0.99),
        "cn+1%": weighted_sse(tt, yy, w, m, s, cn * 1.01),
    }

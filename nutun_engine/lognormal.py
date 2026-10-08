"""The log-normal yield curve and its derivatives (spec §7.4, Cohort sheets columns F..L)."""
from __future__ import annotations

import math

import numpy as np

SQRT_2PI = math.sqrt(2.0 * math.pi)


def phi_z(t: np.ndarray, m: float, s: float) -> tuple[np.ndarray, np.ndarray]:
    z = (np.log(t) - m) / s
    return np.exp(-z * z / 2.0) / (t * s * SQRT_2PI), z


def curve(t: np.ndarray, m: float, s: float, cn: float) -> np.ndarray:
    phi, _ = phi_z(t, m, s)
    return cn * phi


def jacobian(t: np.ndarray, m: float, s: float, cn: float):
    """Returns (f, z, phi, x_m, x_s, x_cn): df/dm = f·z/s, df/ds = f·(z²−1)/s, df/dcn = φ."""
    phi, z = phi_z(t, m, s)
    f = cn * phi
    return f, z, phi, f * z / s, f * (z * z - 1.0) / s, phi


def weighted_sse(t: np.ndarray, y: np.ndarray, w: np.ndarray, m: float, s: float, cn: float) -> float:
    r = y - curve(t, m, s, cn)
    return float(np.sum(w * r * r))

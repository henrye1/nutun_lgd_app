import math

import numpy as np

from nutun_engine.lognormal import SQRT_2PI, curve, jacobian, phi_z, weighted_sse


def test_phi_matches_sheet_formula_at_t1():
    # z(1) = -m/s, phi = exp(-z²/2)/(s√2π)
    m, s = 4.0, 1.7
    phi, z = phi_z(np.array([1.0]), m, s)
    assert z[0] == (math.log(1.0) - m) / s
    assert phi[0] == math.exp(-z[0] ** 2 / 2) / (1.0 * s * SQRT_2PI)


def test_curve_and_jacobian_consistency():
    t = np.arange(1.0, 61.0)
    m, s, cn = 4.0, 1.7, 0.3
    f = curve(t, m, s, cn)
    f2, z, phi, x_m, x_s, x_cn = jacobian(t, m, s, cn)
    np.testing.assert_array_equal(f, f2)
    np.testing.assert_allclose(x_cn, phi)
    np.testing.assert_allclose(x_m, f * z / s)
    h = 1e-6
    np.testing.assert_allclose(x_m, (curve(t, m + h, s, cn) - curve(t, m - h, s, cn)) / (2 * h), rtol=1e-6)
    np.testing.assert_allclose(x_s, (curve(t, m, s + h, cn) - curve(t, m, s - h, cn)) / (2 * h), rtol=1e-6)


def test_weighted_sse_is_sum_of_w_resid_squared():
    t = np.array([1.0, 2.0, 3.0])
    y = np.array([0.01, 0.02, 0.015])
    w = t / t.sum()
    f = curve(t, 1.0, 0.5, 0.1)
    assert weighted_sse(t, y, w, 1.0, 0.5, 0.1) == np.sum(w * (y - f) * (y - f))  # the VBA's association

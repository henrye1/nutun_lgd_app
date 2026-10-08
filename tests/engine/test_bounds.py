from datetime import date

import numpy as np
import pytest
from scipy.stats import t as student_t

from nutun_engine.bounds import cofactor_inverse3, prediction_limits, sensitivity, used_mask
from nutun_engine.lognormal import curve

D = date(2026, 7, 1)
T = np.arange(1.0, 61.0)


def test_used_mask_rules():
    obs = np.array([0.1, 0.2, 0.0, 0.3, 0.0, np.nan])
    keep = np.array([1, 1, 0, 1, 0, 0], bool)
    t = np.arange(1.0, 7.0)
    assert used_mask(t, obs, keep, "KEPT").tolist() == [True, True, False, True, False, False]
    assert used_mask(t, obs, keep, "CONTIGUOUS_PREFIX").tolist() == [True, True, False, False, False, False]
    assert used_mask(t[:2], obs[:2], keep[:2], "CONTIGUOUS_PREFIX").tolist() == [True, True]  # no zero → COUNT
    assert not used_mask(t, np.zeros(6), keep, "CONTIGUOUS_PREFIX").any()  # n = 0


def test_cofactor_inverse_matches_numpy_and_singular():
    V = np.array([[4.0, 1.0, 0.5], [1.0, 3.0, 0.2], [0.5, 0.2, 2.0]])
    W, det = cofactor_inverse3(V)
    np.testing.assert_allclose(W, np.linalg.inv(V), rtol=1e-12)
    assert det == pytest.approx(np.linalg.det(V), rel=1e-12)
    W0, det0 = cofactor_inverse3(np.ones((3, 3)))
    assert det0 == 0 and np.isnan(W0).all()


def _clean(m=4.3, s=1.5, cn=0.25):
    rng = np.random.default_rng(1)
    return curve(T, m, s, cn) * (1 + 0.05 * rng.standard_normal(60))


def test_limits_reproduce_sheet_arithmetic():
    y = _clean()
    keep = np.ones(60, bool)
    b = prediction_limits(T, y, keep, 4.3, 1.5, 0.25, alpha=0.1, p=3, points="KEPT", report_month=D, vb=11)
    assert b.n_points == 60 and b.sum_count == 1830 and b.df == 57
    np.testing.assert_allclose(b.w, T / 1830)
    assert b.sse == pytest.approx(np.sum(b.w * b.resid**2))
    assert b.s_e == pytest.approx(np.sqrt(b.sse / 57)) and b.t_mult == pytest.approx(student_t.ppf(0.95, 57))
    J = np.column_stack([b.x_m, b.x_s, b.x_cn])
    np.testing.assert_allclose(b.V, (J * b.w[:, None]).T @ J, rtol=1e-12)
    i = 10
    h3 = J[i] @ b.W @ J[i]
    assert b.h3[i] == pytest.approx(h3, rel=1e-10) and b.h[i] == b.h3[i]
    assert b.half[i] == pytest.approx(b.t_mult * b.s_e * np.sqrt(1 / b.w[i] + b.h[i]))
    assert b.lower[i] == b.pred[i] - b.half[i] and b.upper[i] == b.pred[i] + b.half[i]


def test_two_parameter_leverage_when_p_is_2():
    y = _clean()
    b = prediction_limits(T, y, np.ones(60, bool), 3.25, 1.2, 0.9, alpha=0.1, p=2, points="KEPT", report_month=D, vb=44)
    assert b.df == 58 and np.array_equal(b.h, b.h2) and not np.array_equal(b.h, b.h3)
    np.testing.assert_allclose(b.Q, np.linalg.inv(b.P), rtol=1e-10)


def test_unused_rows_are_zero_or_blank_and_df_le_0_is_blank():
    y = _clean()
    keep = np.zeros(60, bool)
    keep[:3] = True
    b = prediction_limits(T, y, keep, 4.3, 1.5, 0.25, alpha=0.1, p=3, points="KEPT", report_month=D, vb=11)
    assert b.n_points == 3 and b.df == 0 and np.isnan(b.s_e) and np.isnan(b.t_mult)
    assert np.isnan(b.lower).all() and (b.w[3:] == 0).all() and (b.x_m[3:] == 0).all()
    assert any("df" in w for w in b.warnings)
    with np.errstate(all="raise"):
        prediction_limits(
            T, y, np.zeros(60, bool), 4.3, 1.5, 0.25, alpha=0.1, p=3, points="CONTIGUOUS_PREFIX", report_month=D, vb=11
        )


def test_matrix_t_max_truncates_the_normal_matrix_only():
    y = _clean()
    keep = np.ones(60, bool)
    full = prediction_limits(T, y, keep, 4.3, 1.5, 0.25, alpha=0.1, p=3, points="KEPT", report_month=D, vb=11)
    cut = prediction_limits(T, y, keep, 4.3, 1.5, 0.25, alpha=0.1, p=3, points="KEPT", report_month=D, vb=11,
                            matrix_t_max=50)
    J = np.column_stack([full.x_m, full.x_s, full.x_cn])[:50]
    np.testing.assert_allclose(cut.V, (J * full.w[:50, None]).T @ J, rtol=1e-12)
    assert not np.allclose(cut.V, full.V)
    assert cut.sse == full.sse and cut.n_points == 60 and np.array_equal(cut.w, full.w)  # only V/P change
    cut2 = prediction_limits(T, y, keep, 4.3, 1.5, 0.25, alpha=0.1, p=3, points="KEPT", report_month=D, vb=11,
                             sse_t_max=50)
    assert cut2.sse == pytest.approx(np.sum((full.w * full.resid ** 2)[:50])) and cut2.sse < full.sse
    assert not np.allclose(cut.h3, full.h3) and np.isfinite(cut.lower[55:]).all()
    s_full = sensitivity(T, y, keep, 4.3, 1.5, 0.25, "KEPT")
    s_cut = sensitivity(T, y, keep, 4.3, 1.5, 0.25, "KEPT", t_max=50)
    w = T / T.sum()
    assert s_cut["m+1%"] == pytest.approx(np.sum((w * (y - curve(T, 4.3 * 1.01, 1.5, 0.25)) ** 2)[:50]))
    assert s_cut["m+1%"] < s_full["m+1%"]


def test_sensitivity_is_sse_at_plus_minus_one_percent():
    y = _clean()
    s = sensitivity(T, y, np.ones(60, bool), 4.3, 1.5, 0.25, "KEPT")
    w = T / T.sum()
    assert s["m-1%"] == pytest.approx(np.sum(w * (y - curve(T, 4.3 * 0.99, 1.5, 0.25)) ** 2))
    assert set(s) == {"m-1%", "m+1%", "s-1%", "s+1%", "cn-1%", "cn+1%"}

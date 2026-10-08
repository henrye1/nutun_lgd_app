from datetime import date

import numpy as np
import pytest

from nutun_engine.config import parity_jul26
from nutun_engine.fit import FitResult, fit_block, lm_run, solve3
from nutun_engine.lognormal import curve

D = date(2026, 7, 1)
T = np.arange(1.0, 61.0)


def _synthetic(m=4.3, s=1.5, cn=0.25, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    return curve(T, m, s, cn) * (1 + noise * rng.standard_normal(60))


def test_solve3_partial_pivot_and_singular():
    B = np.array([[0.0, 2.0, 1.0], [1.0, 1.0, 0.0], [3.0, 0.0, 1.0]])
    x = solve3(B, np.array([3.0, 2.0, 4.0]))
    np.testing.assert_allclose(B @ x, [3.0, 2.0, 4.0], atol=1e-12)
    assert solve3(np.zeros((3, 3)), np.ones(3)) is None


def test_lm_recovers_exact_parameters_from_clean_data():
    y = _synthetic()
    w = T / T.sum()
    out = lm_run(T, y, w, 4.0, 1.7, 0.3, mbound=100.0)
    assert out.sse < 1e-20 and abs(out.m - 4.3) < 1e-6 and abs(out.s - 1.5) < 1e-6 and abs(out.cn - 0.25) < 1e-6


def test_lm_holds_m_on_the_bound_when_gradient_pushes_up():
    y = _synthetic(m=4.3)
    w = T / T.sum()
    out = lm_run(T, y, w, 3.0, 1.7, 0.3, mbound=3.25)
    assert out.m == 3.25 and out.sse > 0


def test_lm_fixed_mu_never_moves_m():
    y = _synthetic(m=4.3)
    w = T / T.sum()
    out = lm_run(T, y, w, 4.0, 1.7, 0.3, mbound=100.0, fix_mu=True)
    assert out.m == 4.0 and abs(out.s - 1.5) > 1e-3  # best s, cn given the wrong μ; μ untouched


def test_lm_survives_singular_normal_matrix():
    y = np.zeros(60)
    w = T / T.sum()
    out = lm_run(T, y, w, 4.0, 1.7, 0.3, mbound=100.0)
    assert np.isfinite(out.sse) and out.cn > 1e-9


def test_fit_block_three_param_diagnostics_and_warn():
    cfg = parity_jul26()
    y = _synthetic()
    keep = np.ones(60, dtype=bool)
    r = fit_block(T, y, keep, k=0, report_month=D, vb=11, mode="THREE_PARAM", cfg=cfg)
    assert isinstance(r, FitResult) and r.status == "OK" and r.K == 60 and r.contiguous and r.sum_count == 1830
    assert r.p == 3 and r.df == 57 and r.rule4 == "OK" and r.warn == "" and r.m_at_bound == 0
    assert r.mode_t == pytest.approx(np.exp(r.m - r.s**2))
    assert r.lifetime == pytest.approx(curve(np.arange(1.0, 121.0), r.m, r.s, r.cn).sum())
    row = r.params_row()
    assert row["k"] == 0 and row["vb"] == 11 and row["m"] == r.m and row["Warn"] == ""


def test_fit_block_not_fittable_cases():
    cfg = parity_jul26()
    y = _synthetic()
    few = np.zeros(60, dtype=bool)
    few[:3] = True
    r = fit_block(T, y, few, k=0, report_month=D, vb=11, mode="THREE_PARAM", cfg=cfg)
    assert r.status == "NOT_FITTABLE" and "4" in r.reason and np.isnan(r.m)
    r2 = fit_block(T, y, np.ones(60, bool), k=5, report_month=D, vb=11, mode="TWO_PARAM_FIXED_MU", cfg=cfg, mu=None)
    assert r2.status == "NOT_FITTABLE" and "fixed" in r2.reason.lower()


def test_fit_block_fixed_mu_and_p_rule():
    cfg = parity_jul26()
    y = _synthetic(m=4.3)
    r = fit_block(T, y, np.ones(60, bool), k=0, report_month=D, vb=11, mode="TWO_PARAM_FIXED_MU", cfg=cfg, mu=4.3)
    assert r.m == 4.3 and abs(r.s - 1.5) < 1e-6 and r.p == 3 and r.mu_source == "FIXED_MU_TABLE"
    cfg2 = cfg.model_copy(update={"bounds": cfg.bounds.model_copy(update={"p_rule": "FIXED_MU_IS_2"})})
    r2 = fit_block(T, y, np.ones(60, bool), k=0, report_month=D, vb=11, mode="TWO_PARAM_FIXED_MU", cfg=cfg2, mu=4.3)
    assert r2.p == 2 and r2.df == 58


def test_fit_block_vb44_bound_sets_p2_and_warn():
    cfg = parity_jul26()
    y = _synthetic(m=4.3)
    r = fit_block(T, y, np.ones(60, bool), k=0, report_month=D, vb=44, mode="THREE_PARAM", cfg=cfg)
    assert r.m == 3.25 and r.m_at_bound == 1 and r.p == 2 and r.warn == "CHECK"


def test_manual_mode_uses_given_parameters():
    cfg = parity_jul26()
    y = _synthetic()
    r = fit_block(T, y, np.ones(60, bool), k=0, report_month=D, vb=11, mode="MANUAL", cfg=cfg, manual=(4.3, 1.5, 0.25))
    assert r.status == "MANUAL" and r.m == 4.3 and r.sse == pytest.approx(0.0, abs=1e-30)


def test_fit_is_deterministic():
    cfg = parity_jul26()
    y = _synthetic(noise=0.05)
    a = fit_block(T, y, np.ones(60, bool), k=0, report_month=D, vb=11, mode="THREE_PARAM", cfg=cfg)
    b = fit_block(T, y, np.ones(60, bool), k=0, report_month=D, vb=11, mode="THREE_PARAM", cfg=cfg)
    assert (a.m, a.s, a.cn, a.sse) == (b.m, b.s, b.cn, b.sse)

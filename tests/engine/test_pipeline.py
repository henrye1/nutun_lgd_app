from datetime import date

import numpy as np
import pytest

from nutun_engine.config import parity_jul26
from nutun_engine.lognormal import curve
from nutun_engine.pipeline import CurveRun, run_curves
from tests.engine.synth import make_inputs

D = date(2026, 7, 1)


def _portfolio(n_books=8, months=36, vb=11):
    """n books charged off `months` ago with a log-normal payment profile → every grid point has nHO = n."""
    pays, master, alloc, vbs = [], [], [], []
    t = np.arange(1.0, months + 1.0)
    profile = curve(t, 4.0, 1.5, 0.2) * 1000.0
    for b in range(n_books):
        code = -(1000 + b)
        co = date(2026 - (months // 12), 7, 1)
        master.append((code, co, 1000.0, code))
        c999 = int(f"999{1000 + b}")  # 999-form of -(1000 + b)
        alloc.append((c999, vb, 1000.0, 100.0))
        vbs.append((c999, vb))
        for i in range(months):
            m = date(co.year + (co.month - 1 + i) // 12, (co.month - 1 + i) % 12 + 1, 1)
            if m <= D:
                pays.append((code, code, m, float(profile[i])))
    return make_inputs(payments=pays, master=master, vb_alloc=alloc, vb=vbs)


def _cfg(**curves):
    base = parity_jul26()
    cfg = base.model_copy(update={"curves": base.curves.model_copy(update=curves)})
    return cfg.model_copy(update={"bounds": cfg.bounds.model_copy(update={"params_fit_mode": "THREE_PARAM", "params_k": 0})})


def test_run_curves_three_param_on_synthetic_portfolio():
    inp = _portfolio()
    cfg = _cfg(ma_fit_mode="THREE_PARAM", n_months=3, ma_window=3)
    events = []
    run = run_curves(inp, cfg, D, modes=("THREE_PARAM",), progress=lambda st, k, vb: events.append(st))
    assert isinstance(run, CurveRun) and run.report_month == D
    f = run.fits[("THREE_PARAM", 0, 11)]
    assert f.status == "OK" and abs(f.m - 4.0) < 1e-3 and abs(f.s - 1.5) < 1e-3
    assert run.curve_set.source == "MA_OF_FITS" and run.curve_set.ma_members[11] == [0, 1, 2]
    assert np.isfinite(run.curve_set.C[:, run.curve_set.column(11)]).all()
    assert 11 in run.bounds and np.isfinite(run.curve_set.UB[0, 0])
    assert {"prepare", "grids", "fit", "bounds", "curves"} <= set(events)
    assert set(run.timings) >= {"prepare", "grids", "fit", "bounds", "curves", "total"}
    pf = run.params_frame()
    assert len(pf) == 3 * 6 + 6 and set(pf.vb) == set(cfg.curves.cohorts)
    assert set(pf.grid) == {"ROLLING", "VALUATION_CALC"} and run.calc_fits[("THREE_PARAM", 11)].status == "OK"
    assert len(run.grids_frame()) == (1 + 3) * 60 * 6 and len(run.curves_frame()) == 500 * 6
    bt = run.bounds_table(11)
    assert list(bt.columns)[:4] == ["t", "obs", "keep", "used"] and len(bt) == 60


def test_fixed_mu_without_table_is_not_fittable_and_warns():
    inp = _portfolio()
    base = parity_jul26()
    cfg = base.model_copy(update={"curves": base.curves.model_copy(update={"fixed_mu": [], "n_months": 2, "ma_window": 2})})
    run = run_curves(inp, cfg, D)
    assert run.fits[("TWO_PARAM_FIXED_MU", 0, 11)].status == "NOT_FITTABLE"
    assert run.curve_set.ma_members[11] == [] and np.isnan(run.curve_set.C[:, 0]).all()
    assert any("no fixed" in w.lower() for w in run.warnings)
    cfg_fail = cfg.model_copy(update={"curves": cfg.curves.model_copy(update={"ma_missing": "FAIL"})})
    with pytest.raises(ValueError):
        run_curves(inp, cfg_fail, D)


def test_cohort_without_books_has_no_bounds_and_a_warning():
    inp = _portfolio()
    cfg = _cfg(n_months=2, ma_window=2, ma_fit_mode="THREE_PARAM")
    run = run_curves(inp, cfg, D, modes=("THREE_PARAM",))
    assert 44 not in run.bounds and any("VB44" in w for w in run.warnings)
    assert np.isnan(run.curve_set.UB[:, run.curve_set.column(44)]).all()


def test_run_is_deterministic():
    inp = _portfolio()
    cfg = _cfg(n_months=2, ma_window=2, ma_fit_mode="THREE_PARAM")
    a = run_curves(inp, cfg, D, modes=("THREE_PARAM",))
    b = run_curves(inp, cfg, D, modes=("THREE_PARAM",))
    assert a.params_frame().equals(b.params_frame())
    assert np.array_equal(a.curve_set.C, b.curve_set.C, equal_nan=True)

from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.bounds import prediction_limits
from nutun_engine.config import parity_jul26
from nutun_engine.curves import CurveSet, assemble_curve_set, bound_curves, curve_values, ma_curve
from nutun_engine.fit import fit_block
from nutun_engine.lognormal import curve

D = date(2026, 7, 1)
T = np.arange(1.0, 61.0)
cfg = parity_jul26()


def _fit(k, vb, m, s, cn, mode="MANUAL"):
    y = curve(T, m, s, cn)
    return fit_block(T, y, np.ones(60, bool), k=k, report_month=D, vb=vb, mode=mode, cfg=cfg, manual=(m, s, cn))


def test_curve_values_and_ma_is_mean_of_values_not_parameters():
    f0, f1 = _fit(0, 11, 4.0, 1.5, 0.2), _fit(1, 11, 5.0, 1.7, 0.3)
    t = np.arange(1.0, 501.0)
    np.testing.assert_allclose(curve_values(f0, t), curve(t, 4.0, 1.5, 0.2))
    ma, ks, warns = ma_curve([f0, f1], t, "SKIP_AND_WARN")
    np.testing.assert_allclose(ma, (curve(t, 4.0, 1.5, 0.2) + curve(t, 5.0, 1.7, 0.3)) / 2)
    assert ks == [0, 1] and warns == []
    assert not np.allclose(ma, curve(t, 4.5, 1.6, 0.25))


def test_ma_skips_not_fittable_and_fail_raises():
    f0 = _fit(0, 11, 4.0, 1.5, 0.2)
    bad = fit_block(T, np.zeros(60), np.zeros(60, bool), k=1, report_month=D, vb=11, mode="THREE_PARAM", cfg=cfg)
    assert bad.status == "NOT_FITTABLE"
    ma, ks, warns = ma_curve([f0, bad], np.arange(1.0, 11.0), "SKIP_AND_WARN")
    assert ks == [0] and len(warns) == 1 and "k=1" in warns[0]
    with pytest.raises(ValueError):
        ma_curve([f0, bad], np.arange(1.0, 11.0), "FAIL")
    ma2, ks2, w2 = ma_curve([bad], np.arange(1.0, 11.0), "SKIP_AND_WARN")
    assert np.isnan(ma2).all() and ks2 == [] and len(w2) == 2


def test_bound_curves_blank_outside_used_and_beyond_table():
    y = curve(T, 4.0, 1.5, 0.2)
    keep = np.ones(60, bool)
    keep[50:] = False
    b = prediction_limits(T, y, keep, 4.0, 1.5, 0.2, alpha=0.1, p=3, points="KEPT", report_month=D, vb=11)
    lb, ub = bound_curves(b, 500)
    assert lb.shape == (500,) and np.isnan(lb[50:]).all() and np.isfinite(lb[:50]).all() and ub[0] == b.upper[0]
    lb0, ub0 = bound_curves(None, 10)
    assert np.isnan(lb0).all() and np.isnan(ub0).all()


def test_assemble_ma_of_fits_with_bounds_and_q12():
    fits = {
        ("TWO_PARAM_FIXED_MU", k, vb): _fit(k, vb, 4.0 + 0.1 * k, 1.5, 0.2) for k in range(8) for vb in cfg.curves.cohorts
    }
    y = curve(T, 4.0, 1.5, 0.2)
    bounds = {
        vb: prediction_limits(T, y, np.ones(60, bool), 4.0, 1.5, 0.2, alpha=0.1, p=3, points="KEPT", report_month=D, vb=vb)
        for vb in cfg.curves.cohorts
    }
    cs = assemble_curve_set(cfg, D, fits, bounds)
    assert isinstance(cs, CurveSet) and cs.C.shape == (500, 6) and cs.t[-1] == 500 and cs.source == "MA_OF_FITS"
    assert cs.ma_members[11] == [0, 1, 2, 3, 4, 5]
    t = np.arange(1.0, 501.0)
    np.testing.assert_allclose(
        cs.C[:, 0], np.mean([curve(t, 4.0 + 0.1 * k, 1.5, 0.2) for k in range(6)], axis=0), rtol=1e-14
    )
    assert np.isfinite(cs.UB[:60, 1]).all() and np.isnan(cs.UB[60:, 1]).all()
    pb = cs.paste_block()
    assert list(pb.columns) == [
        "t", "11", "15", "22", "23", "25", "44", "UB 11", "UB 15", "UB 22", "UB 23", "UB 25", "UB 44",
        "LB 11", "LB 15", "LB 22", "LB 23", "LB 25", "LB 44",
    ]
    assert len(pb) == 500
    f = cs.frame()
    assert set(f.columns) == {"vb", "t", "curve", "lb", "ub"} and len(f) == 3000


def test_assemble_single_fit_and_uploaded():
    fits = {("TWO_PARAM_FIXED_MU", 0, vb): _fit(0, vb, 4.0, 1.5, 0.2) for vb in cfg.curves.cohorts}
    c1 = cfg.model_copy(update={"curves": cfg.curves.model_copy(update={"valuation_source": "SINGLE_FIT"})})
    cs = assemble_curve_set(c1, D, fits, {})
    np.testing.assert_allclose(cs.C[:, 0], curve(np.arange(1.0, 501.0), 4.0, 1.5, 0.2))
    assert cs.source == "SINGLE_FIT" and np.isnan(cs.LB).all()
    up = pd.DataFrame(
        {"t": np.arange(1, 501), **{str(vb): np.full(500, 0.001 * i) for i, vb in enumerate(cfg.curves.cohorts, 1)}}
    )
    c2 = cfg.model_copy(update={"curves": cfg.curves.model_copy(update={"valuation_source": "UPLOADED"})})
    cs2 = assemble_curve_set(c2, D, {}, {}, uploaded=up)
    assert cs2.source == "UPLOADED" and cs2.C[0, 0] == 0.001 and cs2.C[0, 5] == 0.006
    with pytest.raises(ValueError):
        assemble_curve_set(c2, D, {}, {}, uploaded=None)


def test_warns_when_a_fit_for_the_ma_window_is_missing():
    fits = {("TWO_PARAM_FIXED_MU", k, vb): _fit(k, vb, 4.0, 1.5, 0.2) for k in range(4) for vb in cfg.curves.cohorts}
    cs = assemble_curve_set(cfg, D, fits, {})
    assert cs.ma_members[11] == [0, 1, 2, 3] and any("VB11" in w and "k=4" in w for w in cs.warnings)

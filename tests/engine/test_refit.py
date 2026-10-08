from datetime import date

import numpy as np
import pytest

from nutun_engine.pipeline import refit_block, run_curves
from tests.engine.test_pipeline import _cfg, _portfolio

D = date(2026, 7, 1)


@pytest.fixture(scope="module")
def base_run():
    return run_curves(_portfolio(), _cfg(ma_fit_mode="THREE_PARAM", n_months=3, ma_window=3), D, modes=("THREE_PARAM",))


def test_manual_refit_changes_the_ma_curve_and_keeps_everything_else(base_run):
    new = refit_block(base_run, grid="ROLLING", k=0, vb=11, mode="MANUAL", manual=(4.5, 1.6, 0.25))
    assert new is not base_run and base_run.fits[("THREE_PARAM", 0, 11)].status == "OK"  # original untouched
    f = new.fits[("MANUAL", 0, 11)]
    assert f.status == "MANUAL" and f.m == 4.5 and ("THREE_PARAM", 0, 11) in new.fits
    # the MA is built from ma_fit_mode (THREE_PARAM) so the curve is unchanged by a MANUAL block
    np.testing.assert_array_equal(new.curve_set.C, base_run.curve_set.C)
    assert "refit" in new.timings and new.report_month == base_run.report_month


def test_refit_in_the_ma_mode_moves_the_curve_and_the_bounds(base_run):
    new = refit_block(base_run, grid="ROLLING", k=0, vb=11, mode="THREE_PARAM", manual=None, mu=None)
    assert new.fits[("THREE_PARAM", 0, 11)].status == "OK"
    bumped = refit_block(base_run, grid="ROLLING", k=0, vb=11, mode="TWO_PARAM_FIXED_MU", mu=5.0)
    assert bumped.fits[("TWO_PARAM_FIXED_MU", 0, 11)].m == 5.0
    cfg2 = base_run.cfg.model_copy(
        update={"curves": base_run.cfg.curves.model_copy(update={"ma_fit_mode": "TWO_PARAM_FIXED_MU"})}
    )
    # with the MA mode switched, only k=0 has a 2P fit → ma_members [0] and a warning for k=1, 2
    run2 = run_curves(_portfolio(), cfg2, D, modes=("THREE_PARAM",))
    run2b = refit_block(run2, grid="ROLLING", k=0, vb=11, mode="TWO_PARAM_FIXED_MU", mu=5.0)
    assert run2b.curve_set.ma_members[11] == [0] and any("k=1" in w for w in run2b.curve_set.warnings)
    assert not np.array_equal(run2b.curve_set.C[:, 0], run2.curve_set.C[:, 0], equal_nan=True)


def test_refit_calc_grid_block_updates_bounds(base_run):
    before = base_run.curve_set.UB[0, 0]
    new = refit_block(base_run, grid="VALUATION_CALC", k=0, vb=11, mode="MANUAL", manual=(4.2, 1.4, 0.21))
    assert new.calc_fits[("MANUAL", 11)].m == 4.2 and base_run.calc_fits.get(("MANUAL", 11)) is None
    # parity bounds take the THREE_PARAM calc fit, so the MANUAL block leaves them unchanged
    assert new.curve_set.UB[0, 0] == before
    # unless the bounds are asked for that mode
    cfg3 = base_run.cfg.model_copy(
        update={"bounds": base_run.cfg.bounds.model_copy(update={"params_fit_mode": "MANUAL", "params_vb_override": {}})}
    )
    run3 = run_curves(_portfolio(), cfg3, D, modes=("THREE_PARAM",))
    assert 11 not in run3.bounds  # no MANUAL fits yet
    run3b = refit_block(run3, grid="VALUATION_CALC", k=0, vb=11, mode="MANUAL", manual=(4.2, 1.4, 0.21))
    assert 11 in run3b.bounds and run3b.bounds_params_from[11] == "VALUATION_CALC MANUAL"


def test_refit_not_fittable_and_bad_keys(base_run):
    nf = refit_block(base_run, grid="ROLLING", k=0, vb=11, mode="TWO_PARAM_FIXED_MU", mu=None)
    assert nf.fits[("TWO_PARAM_FIXED_MU", 0, 11)].status == "NOT_FITTABLE"
    nf2 = refit_block(base_run, grid="ROLLING", k=0, vb=11, mode="MANUAL", manual=None)
    assert nf2.fits[("MANUAL", 0, 11)].status == "NOT_FITTABLE"
    with pytest.raises(ValueError):
        refit_block(base_run, grid="ROLLING", k=9, vb=11, mode="THREE_PARAM")
    with pytest.raises(ValueError):
        refit_block(base_run, grid="ROLLING", k=0, vb=99, mode="THREE_PARAM")

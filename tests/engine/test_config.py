from datetime import date

import pytest
from pydantic import ValidationError

from nutun_engine.config import PRESETS, RunConfig, corrected, load_fixed_mu_seed, parity_jul26


def test_parity_preset_matches_spec_section_8():
    c = parity_jul26()
    assert c.preset == "PARITY_JUL26"
    assert c.run.report_month == date(2026, 7, 1) and c.run.book_list_source == "ACM_VB_ALLOC"
    assert c.payments.vb44_rule == "AS_DELIVERED" and c.payments.exclusion_applied is False
    assert c.payments.exclusion_applied_rolling is True  # Config!B12 is FALSE (boolean); FALSE=0 is FALSE in Excel
    assert c.payments.exclusion_list == [99910293, 99910155]
    assert c.fli.missing_hist_month_calc == "ONE" and c.fli.missing_hist_month_rolling == "DROP_AMOUNT"
    assert c.fli.r2_zero == "ZERO" and c.fli.missing_fwd_month == "ZERO"
    cv = c.curves
    assert cv.cohorts == [11, 15, 22, 23, 25, 44] and cv.n_months == 8 and cv.t_grid == 60
    assert cv.ndata == 61 and cv.max_age == 60 and cv.max_age_vb44 == 61
    assert cv.min_bal_ratio == 0.10 and cv.min_nho == 5 and cv.min_fit_points == 12
    assert cv.vb25_young_age_excl == 3 and cv.calc_offset == 0
    assert cv.offset_basis == "PER_TRANCHE_LAST_PAYMENT"
    assert cv.mbound == {11: 100, 15: 100, 22: 100, 23: 100, 25: 100, 44: 3.25}
    assert cv.alpha == 0.10 and cv.ma_window == 6 and cv.t_max == 500
    assert cv.valuation_source == "MA_OF_FITS" and cv.ma_fit_mode == "TWO_PARAM_FIXED_MU"
    assert c.fit.engine == "LM_PORT" and c.fit.starts[0] == (4.0, 1.7, 0.3) and len(c.fit.starts) == 5
    assert c.bounds.data_rule_set == "VALUATION_CALC" and c.bounds.data_k == 0
    assert c.bounds.params_fit_mode == "THREE_PARAM" and c.bounds.params_k == 1
    assert c.bounds.points == "CONTIGUOUS_PREFIX" and c.bounds.p_rule == "M_AT_BOUND_ONLY"
    assert c.fit.lifetime_horizon == 120
    v = c.valuation
    assert v.horizon == 120 and v.disc_time == 0.43 and v.age_capping == 12 and v.bound_age == 12
    assert v.delta_window == 36 and v.delta_floor == 0.10 and v.month_offset == -2
    assert v.age_basis == "EXAMPLE_MIN" and v.delta_window_alignment == "PAYMENT_MONTH_BACKSTOP"
    assert v.gross_basis == "PP" and v.vb44_own_yield_sub is False
    assert c.capping.age_test == "COUNT_T1" and c.capping.ac_capped_display == "AS_WORKBOOK"
    assert c.costs.vb_map == {22: "22", 44: "44"} and c.costs.default_curve == "Rest"
    assert c.book.vb_source == "ALLOC" and c.forecast.cohort_costs is False
    assert c.results.backtest_n_source == "CLIENT_DELTA_ROWS"


def test_corrected_preset_differs_only_where_spec_says():
    p, c = parity_jul26(), corrected()
    assert c.preset == "CORRECTED"
    assert c.valuation.month_offset == 0 and c.fli.missing_fwd_month == "ONE_AND_WARN"
    assert c.valuation.bound_age is None  # None = AgeCapping
    assert c.bounds.params_k == 0 and c.bounds.data_rule_set == "ROLLING" and c.bounds.points == "KEPT"
    assert c.bounds.p_rule == "FIXED_MU_IS_2"
    assert c.forecast.cohort_costs is True and c.curves.t_max == 600
    assert c.capping.ac_capped_display == "ONLY_WHEN_APPLIES"
    assert c.fli.missing_hist_month_rolling == "ONE"
    assert c.payments.exclusion_applied_rolling is False and c.payments.exclusion_applied is False
    # undecided keys (§19) keep the parity value
    assert c.book.vb_source == p.book.vb_source and c.fli.r2_zero == p.fli.r2_zero
    assert c.valuation.age_basis == p.valuation.age_basis


def test_fixed_mu_seed_has_48_rows_and_known_values():
    rows = load_fixed_mu_seed()
    assert len(rows) == 48
    lk = parity_jul26().fixed_mu_lookup()
    assert lk[(0, 11)] == 4.715979 and lk[(7, 23)] == 14.464980 and lk[(5, 44)] == 3.25
    assert all(r.month == date(2026, 7, 1) for r in rows if r.k == 0)
    assert all(r.month == date(2025, 12, 1) for r in rows if r.k == 7)


def test_config_is_frozen_and_validated():
    c = parity_jul26()
    with pytest.raises(ValidationError):
        c.valuation.__class__(**{**c.valuation.model_dump(), "horizon": 0})
    with pytest.raises(ValidationError):
        RunConfig(preset=1)
    with pytest.raises(ValidationError):
        c.preset = "x"  # frozen
    assert set(PRESETS) == {"PARITY_JUL26", "CORRECTED"}
    assert c.quirk_flags()["Q1.month_offset"] == "-2"
    assert RunConfig.model_validate_json(c.model_dump_json()) == c

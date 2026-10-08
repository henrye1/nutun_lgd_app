from datetime import date

import numpy as np
import pandas as pd

from nutun_engine.config import parity_jul26
from nutun_engine.grids import YieldGrid, aggregate_grid, build_rolling_grids, build_valuation_calc_grid
from nutun_engine.prepare import prepare_rolling, prepare_valuation_calc
from tests.engine.synth import make_inputs

D = date(2026, 7, 1)


def _rows(n_books=6, vb=11, face=100.0, pay=1.0, counts=(1, 2, 3)):
    recs = []
    for _b in range(n_books):
        for c in counts:
            recs.append({"VB": float(vb), "Count": c, "FLIadj": pay, "Face": face, "kmin": 0.0, "kmax": 9.0})
    return pd.DataFrame(recs)


def test_aggregate_sums_counts_and_keep_rule():
    cfg = parity_jul26()
    g = aggregate_grid(_rows(), cfg, "VALUATION_CALC", 0, D)
    assert isinstance(g, YieldGrid) and g.sum_pay.shape == (60, 6) and g.cohorts == (11, 15, 22, 23, 25, 44)
    c = g.column(11)
    assert g.sum_pay[0, c] == 6.0 and g.sum_bal[0, c] == 600.0 and g.n_ho[0, c] == 6
    assert g.yield_[0, c] == 0.01 and g.keep[0, c] and g.constrained[0, c] == 0.01
    assert g.sum_bal[3, c] == 0 and np.isnan(g.yield_[3, c]) and not g.keep[3, c] and g.constrained[3, c] == 0.0
    assert g.n_kept[c] == 3 and g.contiguous[c]
    other = g.column(44)
    assert (g.sum_bal[:, other] == 0).all() and not g.keep[:, other].any() and np.isnan(g.yield_[:, other]).all()


def test_keep_requires_min_nho_and_balance_ratio_and_ndata():
    cfg = parity_jul26()
    rows = pd.concat(
        [
            _rows(n_books=6, counts=(1, 2)),
            _rows(n_books=4, counts=(3,)),  # t=3: nHO 4 < 5
            _rows(n_books=6, counts=(4,), face=5.0),  # t=4: ratio 30/600 < 0.1
        ]
    )
    g = aggregate_grid(rows, cfg, "ROLLING", 0, D)
    c = g.column(11)
    assert g.keep[0, c] and g.keep[1, c] and not g.keep[2, c] and not g.keep[3, c]
    assert g.n_kept[c] == 2 and g.contiguous[c]
    g2 = aggregate_grid(_rows(counts=(1, 3)), cfg, "ROLLING", 0, D)
    assert g2.n_kept[c] == 2 and not g2.contiguous[c]  # kept = {1, 3}, not 1..K
    cfg_small = cfg.model_copy(update={"curves": cfg.curves.model_copy(update={"ndata": 2})})
    g3 = aggregate_grid(_rows(counts=(1, 2, 3)), cfg_small, "ROLLING", 0, D)
    assert g3.keep[:3, c].tolist() == [True, True, False]


def test_nan_amounts_are_dropped_from_sum_but_rows_still_count():
    rows = _rows(n_books=5, counts=(1,))
    rows.loc[0, "FLIadj"] = np.nan
    g = aggregate_grid(rows, parity_jul26(), "ROLLING", 0, D)
    c = g.column(11)
    assert g.sum_pay[0, c] == 4.0 and g.n_ho[0, c] == 5 and g.sum_bal[0, c] == 500.0


def test_vb_outside_cohorts_is_ignored_without_warnings():
    rows = pd.concat([_rows(), _rows(vb=16)])
    with np.errstate(all="raise"):
        g = aggregate_grid(rows, parity_jul26(), "VALUATION_CALC", 0, D)
    assert g.sum_pay.sum() == 18.0


def test_rolling_window_selection_and_report_months():
    pays = [(-100, -10, date(2026, m, 1), 1.0) for m in (5, 6, 7)]
    inp = make_inputs(payments=pays, master=[(-100, date(2026, 4, 10), 100.0, -10)], vb=[(999100, 11)])
    rp = prepare_rolling(inp, parity_jul26(), D)
    grids = build_rolling_grids(rp, parity_jul26(), D)
    assert len(grids) == 8 and [g.k for g in grids] == list(range(8))
    assert grids[1].report_month == date(2026, 6, 1) and grids[7].report_month == date(2025, 12, 1)
    c = grids[0].column(11)
    assert grids[0].n_ho[:3, c].tolist() == [1, 1, 1]  # k=0: all three rows (kmax 2,1,0 ≥ 0)
    assert grids[1].n_ho[:3, c].tolist() == [1, 1, 0]  # k=1: July row has kmax 0 < 1
    assert grids[3].n_ho[:3, c].tolist() == [0, 0, 0]


def test_valuation_calc_grid_uses_include_flag():
    pays = [(-100, -10, date(2026, 7, 1), 1.0), (-300, -30, date(2026, 7, 1), 1.0)]
    inp = make_inputs(
        payments=pays,
        master=[(-100, date(2026, 1, 1), 100.0, -10), (-300, date(2026, 6, 1), 100.0, -30)],
        vb_alloc=[(999100, 11, 100.0, 1.0), (999300, 25, 100.0, 1.0)],
    )
    prep = prepare_valuation_calc(inp, parity_jul26(), D)
    g = build_valuation_calc_grid(prep, parity_jul26(), D)
    assert g.k == 0 and g.rule_set == "VALUATION_CALC" and g.n_ho[0, g.column(11)] == 1
    assert g.n_ho[0, g.column(25)] == 0  # VB25 AgeCO 2 ≤ 3 → not included
    f = g.frame()
    assert set(f.columns) == {
        "rule_set", "k", "report_month", "vb", "t", "sum_pay", "sum_bal", "n_ho", "yield", "keep", "constrained",
    }
    assert len(f) == 360

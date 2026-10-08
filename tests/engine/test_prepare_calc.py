from datetime import date

import pandas as pd

from nutun_engine.config import parity_jul26
from nutun_engine.prepare import prepare_valuation_calc
from tests.engine.synth import make_inputs

D = date(2026, 7, 1)


def _inputs(**kw):
    pays = [
        (-100, -10, date(2026, 3, 1), 10.0),
        (-100, -10, date(2026, 5, 1), 20.0),  # gap in April
        (-100, -10, date(2026, 7, 1), 30.0),
        (-200, -20, date(2026, 7, 1), 5.0),  # charged off this month
        (-300, -30, date(2026, 6, 1), 7.0),
        (-300, -30, date(2026, 7, 1), 8.0),  # VB25, young
    ]
    master = [
        (-100, date(2026, 1, 15), 1000.0, -10),
        (-200, date(2026, 7, 1), 500.0, -20),
        (-300, date(2026, 5, 1), 800.0, -30),
    ]
    alloc = [(999100, 11, 1000.0, 100.0), (999200, 15, 500.0, 50.0), (999300, 25, 800.0, 80.0)]
    return make_inputs(payments=pays, master=master, vb_alloc=alloc, **kw)


def test_columns_keys_and_age():
    out = prepare_valuation_calc(_inputs(), parity_jul26(), D).rows
    assert list(out.columns) == [
        "wClientCode", "CC", "PaymentMonth", "curPayment", "Code999", "CC999", "VB", "ChargeOff", "MaxDate",
        "AgeCO", "Count", "R2", "FLIadj", "Face", "MaxCount", "Excl", "Include",
    ]
    b100 = out[out.wClientCode == -100]
    assert b100.Code999.iloc[0] == 999100 and b100.CC999.iloc[0] == 99910 and b100.VB.iloc[0] == 11
    assert (b100.MaxDate == pd.Timestamp("2026-07-01")).all()
    assert b100.AgeCO.tolist() == [7.0, 7.0, 7.0]  # (2026-07 − 2026-01) + 1, day ignored
    assert b100.Count.tolist() == [1, 2, 3]  # sequential, not calendar
    assert b100.MaxCount.tolist() == [3, 3, 3]
    assert b100.Face.tolist() == [1000.0] * 3 and b100.Include.all()


def test_count_999_once_sequence_exceeds_age_and_exclusion_flags():
    inp = _inputs()
    out = prepare_valuation_calc(inp, parity_jul26(), D).rows
    b200 = out[out.wClientCode == -200]
    assert b200.AgeCO.iloc[0] == 1.0 and b200.Count.iloc[0] == 1 and bool(b200.Include.iloc[0])
    # a 4-row book charged off 2 months ago: row 4 exceeds AgeCO=3 → 999, excluded, MaxCount = 3
    pays = [(-400, -40, date(2026, m, 1), 1.0) for m in (4, 5, 6, 7)]
    inp2 = make_inputs(
        payments=pays, master=[(-400, date(2026, 5, 20), 10.0, -40)], vb_alloc=[(999400, 11, 10.0, 1.0)]
    )
    o = prepare_valuation_calc(inp2, parity_jul26(), D).rows
    assert o.Count.tolist() == [1, 2, 3, 999]
    assert o.Excl.tolist() == [False, False, False, True] and o.MaxCount.tolist() == [3] * 4


def test_vb25_young_age_rule_and_ndata_cap():
    out = prepare_valuation_calc(_inputs(), parity_jul26(), D).rows
    b300 = out[out.wClientCode == -300]
    assert b300.AgeCO.iloc[0] == 3.0 and not b300.Include.any()  # VB25 and AgeCO ≤ 3
    old = make_inputs(
        payments=[(-500, -50, date(2026, 7, 1), 1.0)],
        master=[(-500, date(2021, 1, 1), 10.0, -50)],
        vb_alloc=[(999500, 11, 10.0, 1.0)],
    )
    o = prepare_valuation_calc(old, parity_jul26(), D).rows
    assert o.AgeCO.iloc[0] == 67.0 and not o.Include.iloc[0]  # AgeCO > ndata (61)


def test_fli_factor_missing_month_is_one_and_r2_zero_rule():
    fli = {date(2026, 7, 1): (1.5, 1.0), date(2026, 5, 1): (0.0, 1.0)}  # March missing, May zero
    out = prepare_valuation_calc(_inputs(fli=fli), parity_jul26(), D).rows
    b100 = out[out.wClientCode == -100].set_index("PaymentMonth")
    assert b100.loc["2026-03-01", "R2"] == 1.0 and b100.loc["2026-03-01", "FLIadj"] == 10.0
    assert b100.loc["2026-05-01", "R2"] == 0.0 and b100.loc["2026-05-01", "FLIadj"] == 0.0
    assert b100.loc["2026-07-01", "FLIadj"] == 45.0
    cfg = parity_jul26().model_copy(update={"fli": parity_jul26().fli.model_copy(update={"r2_zero": "ONE"})})
    o2 = prepare_valuation_calc(_inputs(fli=fli), cfg, D).rows.set_index(["wClientCode", "PaymentMonth"])
    assert o2.loc[(-100, "2026-05-01"), "FLIadj"] == 20.0


def test_historical_report_month_drops_later_rows_and_anchors_maxdate():
    out = prepare_valuation_calc(_inputs(), parity_jul26(), date(2026, 5, 1)).rows
    assert out.PaymentMonth.max() == pd.Timestamp("2026-05-01") and len(out) == 2
    assert (out.MaxDate == pd.Timestamp("2026-05-01")).all()
    assert out[out.wClientCode == -100].AgeCO.tolist() == [5.0, 5.0]


def test_book_without_master_row_is_excluded_with_warning():
    inp = make_inputs(
        payments=[(-100, -10, date(2026, 7, 1), 1.0), (-900, -90, date(2026, 7, 1), 1.0)],
        master=[(-100, date(2026, 1, 1), 10.0, -10)],
        vb_alloc=[(999100, 11, 10.0, 1.0)],
    )
    res = prepare_valuation_calc(inp, parity_jul26(), D)
    r = res.rows[res.rows.wClientCode == -900].iloc[0]
    assert pd.isna(r.AgeCO) and pd.isna(r.Face) and r.Excl and not r.Include
    assert any("-900" in w for w in res.warnings)


def test_exclusion_list_applied_only_when_switched_on():
    inp = make_inputs(
        payments=[(-10293, -10293, date(2026, 7, 1), 1.0)],
        master=[(-10293, date(2026, 1, 1), 10.0, -10293)],
        vb_alloc=[(99910293, 11, 10.0, 1.0)],
    )
    assert prepare_valuation_calc(inp, parity_jul26(), D).rows.Include.iloc[0]
    cfg = parity_jul26().model_copy(
        update={"payments": parity_jul26().payments.model_copy(update={"exclusion_applied": True})}
    )
    assert not prepare_valuation_calc(inp, cfg, D).rows.Include.iloc[0]

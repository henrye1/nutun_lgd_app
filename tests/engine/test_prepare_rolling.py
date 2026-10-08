from datetime import date

import numpy as np
import pandas as pd

from nutun_engine.config import parity_jul26
from nutun_engine.prepare import prepare_rolling
from tests.engine.synth import make_inputs

D = date(2026, 7, 1)


def _inputs(**kw):
    pays = [
        (-100, -10, date(2026, 3, 1), 10.0),
        (-100, -10, date(2026, 5, 1), 20.0),
        (-100, -10, date(2026, 7, 1), 30.0),
        (-200, -20, date(2025, 12, 1), 5.0),
        (-200, -20, date(2026, 1, 1), 6.0),  # stopped paying in Jan
    ]
    master = [(-100, date(2026, 1, 15), 1000.0, -10), (-200, date(2019, 3, 31), 500.0, -20)]
    vb = [(999100, 11), (999200, 44)]
    return make_inputs(
        payments=pays, master=master, vb=vb,
        vb_alloc=[(999100, 15, 1000.0, 1.0), (999200, 44, 500.0, 1.0)], **kw,
    )


def test_tranche_keys_use_client_vb_and_month_end_datedif():
    rp = prepare_rolling(_inputs(), parity_jul26(), D)
    tk = rp.tranche_keys.set_index("wClientCode")
    assert list(rp.tranche_keys.columns) == [
        "wClientCode", "MaxPaymentMonth", "Code999", "VB", "ChargeOffDate", "Face", "CC", "CC999", "ExclOK",
        "Age_at_k0", "kmin",
    ]
    assert tk.loc[-100, "VB"] == 11  # ACM_VB (client VB), not ACM_VB_Alloc (15)
    assert tk.loc[-100, "MaxPaymentMonth"] == pd.Timestamp("2026-07-01")
    assert tk.loc[-200, "MaxPaymentMonth"] == pd.Timestamp("2026-01-01")
    assert tk.loc[-100, "Age_at_k0"] == 7 and tk.loc[-100, "kmin"] == 0  # max(0, 7 − 60)
    assert tk.loc[-200, "Age_at_k0"] == 89 and tk.loc[-200, "kmin"] == 28  # VB44: 89 − 61
    assert (tk.ExclOK == 1).all() and tk.loc[-200, "CC999"] == 99920


def test_payment_count_is_calendar_and_kmax_per_tranche():
    p = prepare_rolling(_inputs(), parity_jul26(), D).payments
    b100 = p[p.wClientCode == -100]
    assert b100.Count.tolist() == [1, 3, 5]  # calendar months since first payment
    assert b100.kmax.tolist() == [4, 2, 0]  # months to the tranche's own last payment
    b200 = p[p.wClientCode == -200]
    assert b200.kmax.tolist() == [1, 0] and b200.balance.tolist() == [500.0, 500.0]
    assert b200.kmin.tolist() == [28.0, 28.0]


def test_global_cutoff_offset_basis_rolls_back_from_report_month():
    cfg = parity_jul26().model_copy(
        update={"curves": parity_jul26().curves.model_copy(update={"offset_basis": "GLOBAL_CUTOFF"})}
    )
    p = prepare_rolling(_inputs(), cfg, D).payments
    assert p[p.wClientCode == -200].kmax.tolist() == [7, 6]


def test_q15_month_end_datedif_loses_a_month_for_short_report_months():
    # charge-off 2026-01-20 → EOMONTH 2026-01-31; report Apr-2026 → EOMONTH 2026-04-30; DATEDIF = 2, Age = 3
    inp = make_inputs(
        payments=[(-100, -10, date(2026, 4, 1), 1.0)],
        master=[(-100, date(2026, 1, 20), 10.0, -10)],
        vb=[(999100, 11)],
        vb_alloc=[(999100, 11, 10.0, 1.0)],
    )
    tk = prepare_rolling(inp, parity_jul26(), date(2026, 4, 1)).tranche_keys
    assert tk.Age_at_k0.iloc[0] == 3
    tk_jul = prepare_rolling(inp, parity_jul26(), date(2026, 7, 1)).tranche_keys
    assert tk_jul.Age_at_k0.iloc[0] == 7


def test_missing_fli_month_drops_amount_but_keeps_row():
    fli = {date(2026, 7, 1): (1.5, 1.0), date(2026, 5, 1): (1.0, 1.0)}  # March missing
    p = prepare_rolling(_inputs(fli=fli), parity_jul26(), D).payments
    b100 = p[p.wClientCode == -100].set_index("PaymentMonth")
    assert pd.isna(b100.loc["2026-03-01", "R2"]) and pd.isna(b100.loc["2026-03-01", "FLIadj"])
    assert b100.loc["2026-03-01", "balance"] == 1000.0 and b100.loc["2026-07-01", "FLIadj"] == 45.0
    cfg = parity_jul26().model_copy(
        update={"fli": parity_jul26().fli.model_copy(update={"missing_hist_month_rolling": "ONE"})}
    )
    p2 = prepare_rolling(_inputs(fli=fli), cfg, D).payments.set_index(["wClientCode", "PaymentMonth"])
    assert p2.loc[(-100, "2026-03-01"), "FLIadj"] == 10.0


def test_exclusion_is_live_in_parity_and_switchable():
    inp = make_inputs(
        payments=[(-10293, -10293, date(2026, 7, 1), 1.0)],
        master=[(-10293, date(2026, 1, 1), 10.0, -10293)],
        vb=[(99910293, 11)],
        vb_alloc=[(99910293, 11, 10.0, 1.0)],
    )
    rp = prepare_rolling(inp, parity_jul26(), D)  # parity: the workbook excludes the two books (FALSE=0 is FALSE)
    assert rp.tranche_keys.ExclOK.iloc[0] == 0 and rp.tranche_keys.kmin.iloc[0] == 9999
    cfg = parity_jul26().model_copy(
        update={"payments": parity_jul26().payments.model_copy(update={"exclusion_applied_rolling": False})}
    )
    rp2 = prepare_rolling(inp, cfg, D)
    assert rp2.tranche_keys.ExclOK.iloc[0] == 1 and rp2.tranche_keys.kmin.iloc[0] == 0


def test_missing_chargeoff_gives_nan_kmin_and_warning():
    inp = make_inputs(
        payments=[(-100, -10, date(2026, 7, 1), 1.0)],
        master=[(-100, None, 10.0, -10)],
        vb=[(999100, 11)],
        vb_alloc=[(999100, 11, 10.0, 1.0)],
    )
    rp = prepare_rolling(inp, parity_jul26(), D)
    assert np.isnan(rp.tranche_keys.kmin.iloc[0]) and np.isnan(rp.tranche_keys.Age_at_k0.iloc[0])
    assert any("charge-off" in w for w in rp.warnings)

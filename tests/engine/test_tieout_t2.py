from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.config import parity_jul26
from nutun_engine.dates import from_excel_serial
from nutun_engine.inputs import load_inputs_from_fixtures
from nutun_engine.prepare import prepare_rolling, prepare_valuation_calc

pytestmark = pytest.mark.tieout
D = date(2026, 7, 1)


def _serial_to_ts(s: pd.Series) -> pd.Series:
    return pd.Series(
        [pd.Timestamp(from_excel_serial(v)) if pd.notna(v) else pd.NaT for v in s], index=s.index
    ).astype("datetime64[ns]")


def test_t2a_valuation_calc_rows_match_acm_payments_calc(fixtures_dir):
    inputs = load_inputs_from_fixtures(fixtures_dir)
    res = prepare_valuation_calc(inputs, parity_jul26(), D)
    out = res.rows
    assert res.warnings == []
    calc = pd.read_parquet(fixtures_dir / "valuation" / "calc_rows.parquet")
    calc = calc.sort_values(["wClientCode", "PaymentMonth"], kind="stable").reset_index(drop=True)
    assert len(out) == len(calc) == 55358
    np.testing.assert_array_equal(out.wClientCode.to_numpy(), calc.wClientCode.to_numpy().astype("int64"))
    np.testing.assert_array_equal(out.Code999.to_numpy(), calc.Code999.to_numpy().astype("int64"))
    np.testing.assert_array_equal(out.CC999.to_numpy(), calc.CC999.to_numpy().astype("int64"))
    pd.testing.assert_series_equal(out.VB, calc.vb.astype("float64"), check_names=False)
    pd.testing.assert_series_equal(
        out.ChargeOff, pd.to_datetime(calc.ChargeOff.astype(object)).astype("datetime64[ns]"), check_names=False
    )
    pd.testing.assert_series_equal(out.MaxDate, _serial_to_ts(calc.MaxDate), check_names=False)
    np.testing.assert_array_equal(out.AgeCO.to_numpy(), calc.AgeCO.to_numpy())
    np.testing.assert_array_equal(out.Count.to_numpy(), calc.Count.to_numpy().astype("int64"))
    np.testing.assert_array_equal(out.R2.to_numpy(), calc.R2.to_numpy())
    # 6 cells differ by one ulp: Excel wrote those cached products with 16 significant digits
    np.testing.assert_allclose(out.FLIadj.to_numpy(), calc.FLIadj.to_numpy(), rtol=1e-14, atol=0)
    np.testing.assert_array_equal(out.Face.to_numpy(), calc.Face.to_numpy())
    np.testing.assert_array_equal(out.MaxCount.to_numpy(), calc.MaxCount.to_numpy().astype("int64"))
    np.testing.assert_array_equal(out.Excl.to_numpy().astype(float), calc.Excl.to_numpy())
    np.testing.assert_array_equal(out.Include.to_numpy().astype(float), calc.Include.to_numpy())
    # spot values from the spec / sheet
    r0 = out.iloc[0]
    assert r0.wClientCode == -1075810 and r0.Code999 == 9991075810 and r0.CC999 == 99910758 and r0.VB == 25
    assert r0.AgeCO == 1 and r0.Count == 1 and r0.R2 == 1.04272635628913 and r0.Face == 4866529.55
    assert not r0.Include


@pytest.mark.parametrize("wb", ["rolling_2p", "rolling_3p"])
def test_t2b_rolling_rows_and_tranche_keys_match_workbook(fixtures_dir, wb):
    inputs = load_inputs_from_fixtures(fixtures_dir)
    rp = prepare_rolling(inputs, parity_jul26(), D)
    assert rp.warnings == []
    tk_fx = pd.read_parquet(fixtures_dir / wb / "Tranche_Keys.parquet")
    tk_fx["wClientCode"] = tk_fx.wClientCode.astype("int64")
    m = rp.tranche_keys.merge(tk_fx, on="wClientCode", suffixes=("", "_wb"), how="outer", indicator=True)
    assert (m["_merge"] == "both").all() and len(m) == 550
    pd.testing.assert_series_equal(m.MaxPaymentMonth, _serial_to_ts(m.MaxPaymentMonth_wb), check_names=False)
    np.testing.assert_array_equal(m.Code999.to_numpy(), m.Code999_wb.to_numpy().astype("int64"))
    pd.testing.assert_series_equal(m.VB, m.VB_wb.astype("float64"), check_names=False)
    pd.testing.assert_series_equal(m.ChargeOffDate, _serial_to_ts(m.ChargeOffDate_wb), check_names=False)
    np.testing.assert_array_equal(m.Face.to_numpy(), m.Face_wb.to_numpy())
    np.testing.assert_array_equal(m.CC999.to_numpy(), m.CC999_wb.to_numpy())
    np.testing.assert_array_equal(m.ExclOK.to_numpy(), m.ExclOK_wb.to_numpy())
    np.testing.assert_array_equal(m.Age_at_k0.to_numpy(), m.Age_at_k0_wb.to_numpy())
    np.testing.assert_array_equal(m.kmin.to_numpy(), m.kmin_wb.to_numpy())

    pay_fx = pd.read_parquet(fixtures_dir / wb / "ACM_Payments.parquet")
    pay_fx = pay_fx.sort_values(["wClientCode", "PaymentMonth"], kind="stable").reset_index(drop=True)
    p = rp.payments
    assert len(p) == len(pay_fx) == 55358
    np.testing.assert_array_equal(p.wClientCode.to_numpy(), pay_fx.wClientCode.to_numpy().astype("int64"))
    pd.testing.assert_series_equal(p.VB, pay_fx.vb.astype("float64"), check_names=False)
    np.testing.assert_array_equal(p.Count.to_numpy(), pay_fx.Count.to_numpy().astype("int64"))
    np.testing.assert_array_equal(p.R2.to_numpy(), pay_fx.R2.to_numpy())  # NaN == NaN under array_equal
    np.testing.assert_allclose(p.FLIadj.to_numpy(), pay_fx.FLIadj.to_numpy(), rtol=1e-14, atol=0)
    np.testing.assert_array_equal(p.balance.to_numpy(), pay_fx.balance.to_numpy())
    np.testing.assert_array_equal(p.kmin.to_numpy(), pay_fx.kmin.to_numpy())
    np.testing.assert_array_equal(p.kmax.to_numpy(), pay_fx.kmax.to_numpy().astype("int64"))

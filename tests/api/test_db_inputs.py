from datetime import date

import pandas as pd
import pytest

from api.db_inputs import TABLE_SQL, load_inputs, read_vb_override_csv
from nutun_engine.inputs import RunInputs, validate_inputs


def _fake_tables():
    return {
        "payments": pd.DataFrame(
            {"wClientCode": [-100], "CC": [-10], "PaymentMonth": [pd.Timestamp("2026-07-01")], "curPayment": [5.0]}
        ),
        "payments_vb44_excluded": pd.DataFrame(
            columns=["wClientCode", "CC", "PaymentMonth", "curPayment", "Rows_Excluded", "ReportingMonth", "Reason"]
        ),
        "master": pd.DataFrame(
            {
                "wClientCode": [-100], "dtChargeOffDate": ["2026-01-05"], "curOriginalCapital": [10.0],
                "curChargeOffAmount": [9.0], "curInterest": [0.0], "curLegalFees": [0.0],
                "dtLastPayment": ["2026-07-02"], "naccounts": [1], "Code999": [999100], "CustomerCode": [-10],
                "Customers": [1],
            }
        ),
        "universe": pd.DataFrame(
            {
                "BookCode": [-100], "Code999": [999100], "CustomerCode": [-10], "Customers": [1], "MasterRows": [1],
                "Accounts": [1], "Face": [10.0], "FirstChargeOff": [pd.Timestamp("2026-01-05")],
                "LastPayment": [pd.Timestamp("2026-07-02")],
            }
        ),
        "vb": pd.DataFrame({"wClientCode": [999100], "VB": [11]}),
        "vb_alloc": pd.DataFrame(
            {"wClientCode": [999100], "BookCode": [-100], "VB": [11], "VB_raw": [11], "Face": [10.0], "PP": [1.0]}
        ),
        "caeir": pd.DataFrame({"wClientCode": [999100], "CAEIR": [0.2], "PP": [1.0]}),
        "fli": pd.DataFrame({"Date": [pd.Timestamp("2026-07-01")], "R2": [1.0], "Adj": [1.0]}),
        "costs": pd.DataFrame({"T": [1], "Cost": [0.05]}),
        "costs_cohorts": pd.DataFrame({"VB": [22], "T": [1], "Cost": [0.04]}),
        "capping": pd.DataFrame({"T": [1], "VB": [11], "LB": [0.5], "UB": [1.5]}),
        "acm_config": pd.DataFrame({"Name": ["AgeCapping", "disc_time"], "Value": ["12", "0.43"]}),
        "info": pd.DataFrame({"wClientCode": [999100], "VB": [11], "Age": [7], "CAEIR": [0.2], "Cost": [1.0]}),
    }


def test_load_inputs_runs_every_select_and_canonicalises():
    tables, seen = _fake_tables(), []

    def fetch(sql, params):
        seen.append((sql, params))
        key = next(k for k, s in TABLE_SQL.items() if s == sql)
        return tables[key]

    inp = load_inputs(fetch, date(2026, 7, 1))
    assert isinstance(inp, RunInputs) and len(seen) == len(TABLE_SQL)
    assert all(s.lstrip().upper().startswith("SELECT") for s, _ in seen)
    assert inp.master.dtChargeOffDate.dtype == "datetime64[ns]" and inp.payments.wClientCode.dtype == "int64"
    assert inp.acm_config == {"AgeCapping": "12", "disc_time": "0.43"}
    assert list(inp.vb_override.columns) == ["wClientCode", "VB", "VB_raw"] and inp.vb_override.empty
    assert any(p == {"d": date(2026, 7, 1)} for _, p in seen)
    assert validate_inputs(inp) == []


def test_vb_override_csv(tmp_path):
    p = tmp_path / "ov.csv"
    p.write_text("wClientCode,VB,VB_raw\n999000001,15,15\n999000002,44,\n")
    ov = read_vb_override_csv(p)
    assert ov.wClientCode.tolist() == [999000001, 999000002] and ov.VB.tolist() == [15.0, 44.0]
    assert pd.isna(ov.VB_raw.iloc[1])
    with pytest.raises(ValueError):
        read_vb_override_csv(tmp_path / "missing.csv")

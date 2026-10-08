from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.inputs import (
    RunInputs,
    code999,
    load_inputs_from_fixtures,
    lookup_vb,
    to_date,
    to_month,
    validate_inputs,
)
from tests.engine.synth import make_inputs


def test_code999_forms():
    s = pd.Series([-10720, 46, -1075810, 998, -10293], dtype="int64")
    assert code999(s).tolist() == [99910720, 46, 9991075810, 998, 99910293]
    assert code999(s).dtype == "int64"


def test_to_month_accepts_serials_strings_and_datetimes():
    out = to_month(pd.Series([46204.0, "2026-07-15", pd.Timestamp("2025-09-01"), None]))
    assert out.tolist()[:3] == [pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-01"), pd.Timestamp("2025-09-01")]
    assert pd.isna(out.iloc[3])
    d = to_date(pd.Series([41707.0, "2014-03-09", ""]))
    assert d.iloc[0] == pd.Timestamp("2014-03-09") and d.iloc[1] == pd.Timestamp("2014-03-09") and pd.isna(d.iloc[2])


def test_lookup_vb_override_wins_even_when_blank():
    override = pd.DataFrame({"wClientCode": [99910722, 99910731], "VB": [15.0, np.nan], "VB_raw": [15.0, np.nan]})
    source = pd.DataFrame({"wClientCode": [99910722, 99910731, 46], "VB": [11.0, 44.0, 15.0]})
    out = lookup_vb(pd.Series([99910722, 99910731, 46, 1], dtype="int64"), override, source)
    assert out.tolist()[0] == 15.0 and pd.isna(out.iloc[1]) and out.iloc[2] == 15.0 and pd.isna(out.iloc[3])


def test_synthetic_inputs_validate_clean():
    inp = make_inputs(
        payments=[(-100, -10, date(2026, 6, 1), 10.0), (-100, -10, date(2026, 7, 1), 12.0)],
        master=[(-100, date(2026, 5, 3), 1000.0, -10)],
        vb_alloc=[(999100, 11, 1000.0, 500.0)],
    )
    assert isinstance(inp, RunInputs)
    assert validate_inputs(inp) == []
    assert inp.payments.PaymentMonth.dtype == "datetime64[ns]" and inp.payments.wClientCode.dtype == "int64"


def test_validate_flags_bad_months_and_missing_master():
    inp = make_inputs(
        payments=[(-100, -10, date(2026, 6, 15), 10.0), (-200, -20, date(2026, 7, 1), 1.0)],
        master=[(-100, date(2026, 5, 3), 1000.0, -10)],
    )
    w = validate_inputs(inp)
    assert any("first of the month" in x for x in w)
    assert any("-200" in x and "ACM_Master" in x for x in w)


@pytest.mark.tieout
def test_fixture_loader_shapes_and_types(fixtures_dir):
    inp = load_inputs_from_fixtures(fixtures_dir)
    assert len(inp.payments) == 55358 and inp.payments.PaymentMonth.max() == pd.Timestamp("2026-07-01")
    assert inp.payments.wClientCode.dtype == "int64" and inp.payments.curPayment.dtype == "float64"
    assert len(inp.master) == 555 and inp.master.dtChargeOffDate.dtype == "datetime64[ns]"
    assert len(inp.vb_alloc) == 538 and len(inp.info) == 539 and len(inp.fli) == 327
    assert inp.fli.Date.min() == pd.Timestamp("2012-08-01")
    assert inp.acm_config["AgeCapping"] == "12" and inp.acm_config["disc_time"] == "0.43"
    assert validate_inputs(inp) == []

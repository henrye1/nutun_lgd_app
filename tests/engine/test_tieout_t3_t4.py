from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.config import parity_jul26
from nutun_engine.grids import build_rolling_grids, build_valuation_calc_grid
from nutun_engine.inputs import load_inputs_from_fixtures
from nutun_engine.prepare import prepare_rolling, prepare_valuation_calc

pytestmark = pytest.mark.tieout
D = date(2026, 7, 1)
VBS = (11, 15, 22, 23, 25, 44)


def _check_grid(g, fx: pd.DataFrame, label: str):
    assert fx["t"].tolist() == list(range(1, 61))
    for vb in VBS:
        c = g.column(vb)
        np.testing.assert_allclose(
            g.sum_pay[:, c], fx[f"pay_{vb}"].to_numpy(), rtol=1e-12, atol=0, err_msg=f"{label} pay {vb}"
        )
        np.testing.assert_allclose(
            g.sum_bal[:, c], fx[f"bal_{vb}"].to_numpy(), rtol=1e-12, atol=0, err_msg=f"{label} bal {vb}"
        )
        np.testing.assert_array_equal(
            g.n_ho[:, c], fx[f"nho_{vb}"].to_numpy().astype("int64"), err_msg=f"{label} nHO {vb}"
        )
        wb_yield = fx[f"yld_{vb}"].to_numpy(dtype="float64")  # "" (division by zero) → NaN
        np.testing.assert_allclose(
            g.yield_[:, c], wb_yield, rtol=1e-12, atol=0, equal_nan=True, err_msg=f"{label} yield {vb}"
        )
        np.testing.assert_array_equal(
            g.keep[:, c], (fx[f"keep_{vb}"] == "KEPT").to_numpy(), err_msg=f"{label} keep {vb}"
        )
        np.testing.assert_allclose(
            g.constrained[:, c], fx[f"cy_{vb}"].to_numpy(dtype="float64"), rtol=1e-12, atol=0,
            err_msg=f"{label} constrained {vb}",
        )


def test_t3_valuation_calc_grid_matches_calc_sheet(fixtures_dir, expected):
    inputs = load_inputs_from_fixtures(fixtures_dir)
    cfg = parity_jul26()
    g = build_valuation_calc_grid(prepare_valuation_calc(inputs, cfg, D), cfg, D)
    fx = pd.read_parquet(fixtures_dir / "valuation" / "calc_grid.parquet")
    _check_grid(g, fx, "calc")
    c = g.column(11)
    assert g.sum_pay[0, c] == pytest.approx(expected["calc_grid_pay_11_t1"], rel=1e-12)
    assert g.sum_bal[0, c] == pytest.approx(expected["calc_grid_bal_11_t1"], rel=1e-12) and g.keep[0, c]
    assert g.n_kept[c] == 55 and g.contiguous[c]  # Cohort_11!B8/B9 in the valuation workbook


@pytest.mark.parametrize("wb", ["rolling_2p", "rolling_3p"])
def test_t4_rolling_grids_match_yields_sheets(fixtures_dir, expected, wb):
    inputs = load_inputs_from_fixtures(fixtures_dir)
    cfg = parity_jul26()
    grids = build_rolling_grids(prepare_rolling(inputs, cfg, D), cfg, D)
    expected_K = {0: [55, 55, 57, 45, 28, 49], 7: [52, 49, 54, 39, 30, 47]}  # Appendix B, k = 0 and k = 7
    for k, g in enumerate(grids):
        fx = pd.read_parquet(fixtures_dir / wb / f"Yields_M{k}.parquet")
        _check_grid(g, fx, f"{wb} k={k}")
        if k in expected_K:
            assert g.n_kept.tolist() == expected_K[k]
    assert grids[0].yield_[0, grids[0].column(11)] == pytest.approx(expected["rolling_k0_yield_11_t1"], rel=1e-12)

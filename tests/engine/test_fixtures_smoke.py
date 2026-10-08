import json

import pandas as pd
import pytest

pytestmark = pytest.mark.tieout


def test_manifest_row_counts(fixtures_dir):
    m = json.loads((fixtures_dir / "manifest.json").read_text())
    v = m["valuation"]["tables"]
    assert v["ACM_Payments"]["rows"] == 55358
    assert v["ACM_Master"]["rows"] == 555
    assert v["ACM_VB_Alloc"]["rows"] == 538
    assert v["ACM_VB"]["rows"] == 539
    assert v["ACM_CAEIR"]["rows"] == 539
    assert v["ACM_FLI"]["rows"] == 327
    assert v["ACM_Capping"]["rows"] == 192
    assert v["ACM_Costs"]["rows"] == 1000
    assert v["ACM_Costs_Cohorts"]["rows"] == 2000
    assert v["Info"]["rows"] == 539
    assert v["calc_rows"]["rows"] == 55358
    assert v["calc_grid"]["rows"] == 60
    assert v["Curves"]["rows"] == 500
    for key in ("rolling_2p", "rolling_3p"):
        r = m[key]["tables"]
        assert r["ACM_Payments"]["rows"] == 55358
        assert r["Tranche_Keys"]["rows"] == 550
        assert r["Params"]["rows"] == 48
        for k in range(8):
            assert r[f"Yields_M{k}"]["rows"] == 60


def test_known_cells_survive_extraction(fixtures_dir):
    grid = pd.read_parquet(fixtures_dir / "valuation" / "calc_grid.parquet")
    assert grid.loc[0, "t"] == 1
    assert grid.loc[0, "pay_11"] == 5577076.2510529701
    assert grid.loc[0, "nho_11"] == 24
    assert grid.loc[0, "keep_11"] == "KEPT"
    y0 = pd.read_parquet(fixtures_dir / "rolling_2p" / "Yields_M0.parquet")
    assert y0.loc[0, "bal_11"] == 7465357592.2900019  # the sheet's cached value (spec prints it rounded)
    params = pd.read_parquet(fixtures_dir / "rolling_2p" / "Params.parquet")
    assert params.loc[0, "m"] == pytest.approx(4.715979, abs=1e-9)
    assert params.loc[0, "K"] == 55
    info = pd.read_parquet(fixtures_dir / "valuation" / "Info.parquet")
    assert round(float(info["Cost"].sum()), 2) == 8507208539.81

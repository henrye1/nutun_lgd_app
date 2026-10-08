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


def test_known_cells_survive_extraction(fixtures_dir, expected):
    grid = pd.read_parquet(fixtures_dir / "valuation" / "calc_grid.parquet")
    assert grid.loc[0, "t"] == 1
    assert grid.loc[0, "pay_11"] == expected["calc_grid_pay_11_t1"]
    assert grid.loc[0, "nho_11"] == 24
    assert grid.loc[0, "keep_11"] == "KEPT"
    y0 = pd.read_parquet(fixtures_dir / "rolling_2p" / "Yields_M0.parquet")
    assert y0.loc[0, "bal_11"] == expected["calc_grid_bal_11_t1"]  # the sheet's cached value, not the rounded one
    params = pd.read_parquet(fixtures_dir / "rolling_2p" / "Params.parquet")
    assert params.loc[0, "m"] == pytest.approx(4.715979, abs=1e-9)
    assert params.loc[0, "K"] == 55
    info = pd.read_parquet(fixtures_dir / "valuation" / "Info.parquet")
    assert round(float(info["Cost"].sum()), 2) == expected["info_sum_cost"]


def test_m2_fixture_tables_present(fixtures_dir):
    m = json.loads((fixtures_dir / "manifest.json").read_text())
    for key in ("rolling_2p", "rolling_3p"):
        t = m[key]["tables"]
        for vb in (11, 15, 22, 23, 25, 44):
            for k in range(8):
                assert t[f"cohort_{vb}_k{k}_table"]["rows"] == 60
                assert t[f"cohort_{vb}_k{k}_pred120"]["rows"] == 120
                assert t[f"cohort_{vb}_k{k}_panel"]["rows"] > 30
        assert t["Curves_k"]["rows"] == 120 and t["Curves_MA6"]["rows"] == 120
        assert t["Curve_MA6_350"]["rows"] == 350
    v = m["valuation"]["tables"]
    for vb in (11, 15, 22, 23, 25, 44):
        assert v[f"cohort_{vb}_table"]["rows"] == 75 and v[f"cohort_{vb}_panel"]["rows"] > 20


def test_m2_known_block_cells(fixtures_dir, expected):
    tbl = pd.read_parquet(fixtures_dir / "rolling_2p" / "cohort_11_k0_table.parquet")
    assert tbl.loc[0, "t"] == 1 and tbl.loc[0, "used"] == 1
    assert tbl.loc[0, "pred"] == pytest.approx(expected["rolling_k0_vb11_2p"]["cn"] * tbl.loc[0, "phi"], rel=1e-12)
    panel = pd.read_parquet(fixtures_dir / "rolling_2p" / "cohort_11_k0_panel.parquet").set_index(["row", "col"])
    assert panel.loc[(3, "B"), "value_num"] == expected["rolling_k0_vb11_2p"]["mu"]
    assert panel.loc[(11, "B"), "value_num"] == expected["rolling_k0_vb11_2p"]["sse"]
    k1 = pd.read_parquet(fixtures_dir / "rolling_2p" / "cohort_11_k1_panel.parquet").set_index(["row", "col"])
    assert k1.loc[(3, "Z"), "value_num"] == expected["rolling_k1_vb11_2p"]["mu"]
    vp = pd.read_parquet(fixtures_dir / "valuation" / "cohort_11_panel.parquet").set_index(["row", "col"])
    assert vp.loc[(4, "B"), "value_num"] == expected["valuation_cohort11"]["m"]
    assert vp.loc[(13, "AF"), "value_num"] == expected["valuation_cohort11"]["W11"]
    ma = pd.read_parquet(fixtures_dir / "rolling_2p" / "Curves_MA6.parquet")
    assert float(ma.loc[0, "11_M0"]) == expected["ma6_2p_vb11_t1"]
    c350 = pd.read_parquet(fixtures_dir / "rolling_2p" / "Curve_MA6_350.parquet")
    assert c350.loc[0, "t"] == 1 and c350.loc[349, "t"] == 350
    assert c350.loc[0, "11_MA6"] == pytest.approx(expected["ma6_2p_vb11_t1"], rel=1e-12)

from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.bounds import prediction_limits
from nutun_engine.config import parity_jul26
from nutun_engine.curves import assemble_curve_set
from nutun_engine.fit import fit_block, fit_grid
from nutun_engine.grids import build_rolling_grids, build_valuation_calc_grid
from nutun_engine.inputs import load_inputs_from_fixtures
from nutun_engine.lognormal import curve
from nutun_engine.prepare import prepare_rolling, prepare_valuation_calc
from scripts.xlsx_stream import idx_to_col

pytestmark = pytest.mark.tieout
D = date(2026, 7, 1)
VBS = (11, 15, 22, 23, 25, 44)


def _wb_params(fixtures_dir, wb):
    out = {}
    for vb in VBS:
        for k in range(8):
            p = pd.read_parquet(fixtures_dir / wb / f"cohort_{vb}_k{k}_panel.parquet").set_index(["row", "col"])
            col = idx_to_col(2 + 24 * k)
            out[(k, vb)] = tuple(float(p.loc[(r, col), "value_num"]) for r in (3, 4, 5))
    return out


def _manual_fits(fixtures_dir, wb, cfg, mode="TWO_PARAM_FIXED_MU"):
    T = np.arange(1.0, 61.0)
    return {
        (mode, k, vb): fit_block(
            T, np.zeros(60), np.ones(60, bool), k=k, report_month=D, vb=vb, mode="MANUAL", cfg=cfg, manual=prm
        )
        for (k, vb), prm in _wb_params(fixtures_dir, wb).items()
    }


def test_t6_per_k_curves_and_ma6_match_2p_workbook(fixtures_dir, expected):
    cfg = parity_jul26()
    prm = _wb_params(fixtures_dir, "rolling_2p")
    t120 = np.arange(1.0, 121.0)
    ck = pd.read_parquet(fixtures_dir / "rolling_2p" / "Curves_k.parquet")
    ma = pd.read_parquet(fixtures_dir / "rolling_2p" / "Curves_MA6.parquet")
    for vb in VBS:
        for k in range(8):
            np.testing.assert_allclose(
                curve(t120, *prm[(k, vb)]), ck[f"{vb}_M{k}"].to_numpy(dtype=float), rtol=1e-12, atol=0
            )
        for k in range(3):
            want = pd.to_numeric(ma[f"{vb}_M{k}"], errors="coerce").to_numpy(dtype=float)
            got = np.mean([curve(t120, *prm[(j, vb)]) for j in range(k, k + 6)], axis=0)
            np.testing.assert_allclose(got, want, rtol=1e-12, atol=0, err_msg=f"MA6 VB{vb} k={k}")
    c350 = pd.read_parquet(fixtures_dir / "rolling_2p" / "Curve_MA6_350.parquet")
    t350 = np.arange(1.0, 351.0)
    for vb in VBS:
        got = np.mean([curve(t350, *prm[(j, vb)]) for j in range(6)], axis=0)
        np.testing.assert_allclose(got, c350[f"{vb}_MA6"].to_numpy(dtype=float), rtol=1e-12, atol=0)
    fits = _manual_fits(fixtures_dir, "rolling_2p", cfg)
    cs = assemble_curve_set(cfg, D, fits, {})
    assert cs.C[0, cs.column(11)] == pytest.approx(expected["ma6_2p_vb11_t1"], rel=1e-12)
    assert cs.C[:350, cs.column(11)].sum() == pytest.approx(expected["ma6_350_vb11_lifetime"], rel=1e-12)


def test_t6_fitted_ma6_matches_workbook_to_fit_tolerance(fixtures_dir):
    cfg = parity_jul26()
    inputs = load_inputs_from_fixtures(fixtures_dir)
    grids = build_rolling_grids(prepare_rolling(inputs, cfg, D), cfg, D)
    fits = {
        ("TWO_PARAM_FIXED_MU", r.k, r.vb): r
        for g in grids
        for r in fit_grid(g, cfg, "TWO_PARAM_FIXED_MU", cfg.fixed_mu_lookup())
    }
    cs = assemble_curve_set(cfg, D, fits, {})
    ma = pd.read_parquet(fixtures_dir / "rolling_2p" / "Curves_MA6.parquet")
    for vb in VBS:
        want = pd.to_numeric(ma[f"{vb}_M0"], errors="coerce").to_numpy(dtype=float)
        np.testing.assert_allclose(cs.C[:120, cs.column(vb)], want, rtol=1e-5, atol=0, err_msg=f"VB{vb}")


def test_t6b_ma6_to_t500_reproduces_client_curve(fixtures_dir, expected):
    cfg = parity_jul26()
    cs = assemble_curve_set(cfg, D, _manual_fits(fixtures_dir, "rolling_2p", cfg), {})
    client = pd.read_parquet(fixtures_dir / "valuation" / "Curves.parquet")
    # Finding (2026-10-08): the "client curve = MA6 of fixed-mu fits" hypothesis (spec §2.2) holds for VB11,
    # VB22 and VB25 (~1e-6), is 0.08% off for VB15, and does NOT hold for VB23 (25%) and VB44 (46%): the pasted
    # client curves for those cohorts come from somewhere else. The per-VB tolerance lives in the private JSON.
    tol = expected["t6b_client_curve_max_rel_tol"]
    report = {}
    for vb in VBS:
        want = client[f"c_{vb}"].to_numpy(dtype=float)
        got = cs.C[:, cs.column(vb)]
        rel = float(np.nanmax(np.abs(got - want) / np.abs(want)))
        report[vb] = rel
        if tol[str(vb)] is not None:
            assert rel <= tol[str(vb)], f"client curve VB{vb}: max rel {rel:.2e} > {tol[str(vb)]}"
    print("T6b max rel diff MA6(2P) vs Curves!B:G: " + ", ".join(f"VB{vb} {r:.2e}" for vb, r in report.items()))
    assert report[23] > 0.1 and report[44] > 0.1  # keep the finding visible: a fix that closes it must update this
    assert cs.C[0, cs.column(11)] == pytest.approx(expected["client_curve_vb11_t1"], rel=1e-5)
    assert cs.C[59, cs.column(11)] == pytest.approx(expected["client_curve_vb11_t60"], rel=1e-5)


def test_t7_bound_curves_match_curves_sheet(fixtures_dir, expected):
    cfg = parity_jul26()
    inputs = load_inputs_from_fixtures(fixtures_dir)
    g = build_valuation_calc_grid(prepare_valuation_calc(inputs, cfg, D), cfg, D)
    bounds = {}
    for vb in VBS:
        p = pd.read_parquet(fixtures_dir / "valuation" / f"cohort_{vb}_panel.parquet").set_index(["row", "col"])
        m, s, cn = (float(p.loc[(r, "B"), "value_num"]) for r in (4, 5, 6))
        pp = int(p.loc[(13, "J"), "value_num"])
        c = g.column(vb)
        bounds[vb] = prediction_limits(
            g.t, g.constrained[:, c], g.keep[:, c], m, s, cn, alpha=cfg.curves.alpha, p=pp,
            points="CONTIGUOUS_PREFIX", report_month=D, vb=vb, matrix_t_max=cfg.bounds.matrix_t_max[vb],
            sse_t_max=cfg.bounds.sse_t_max[vb],
        )
    cs = assemble_curve_set(cfg, D, _manual_fits(fixtures_dir, "rolling_2p", cfg), bounds)
    client = pd.read_parquet(fixtures_dir / "valuation" / "Curves.parquet")
    for vb in VBS:
        c = cs.column(vb)
        np.testing.assert_allclose(
            cs.UB[:, c], client[f"ub_{vb}"].to_numpy(dtype=float), rtol=1e-10, atol=0, equal_nan=True, err_msg=f"UB {vb}"
        )
        np.testing.assert_allclose(
            cs.LB[:, c], client[f"lb_{vb}"].to_numpy(dtype=float), rtol=1e-10, atol=0, equal_nan=True, err_msg=f"LB {vb}"
        )
    e = expected["valuation_cohort11"]
    assert cs.UB[0, cs.column(11)] == pytest.approx(e["upper_1"], rel=1e-10)
    assert cs.LB[0, cs.column(11)] == pytest.approx(e["lower_1"], rel=1e-10)

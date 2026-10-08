from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.config import parity_jul26
from nutun_engine.inputs import load_inputs_from_fixtures
from nutun_engine.pipeline import run_curves

pytestmark = pytest.mark.tieout
D = date(2026, 7, 1)
VBS = (11, 15, 22, 23, 25, 44)


def test_parity_curve_run_end_to_end(fixtures_dir, expected):
    inputs = load_inputs_from_fixtures(fixtures_dir)
    cfg = parity_jul26()
    run = run_curves(inputs, cfg, D)
    assert len(run.fits) == 2 * 8 * 6 and all(f.status == "OK" for f in run.fits.values())
    assert run.timings["total"] < 20.0
    client = pd.read_parquet(fixtures_dir / "valuation" / "Curves.parquet")
    tol = expected["t6b_client_curve_max_rel_tol"]
    for vb in VBS:
        if tol[str(vb)] is None:
            continue  # VB23 / VB44: the client curve is not the 2P MA6 (see T6b)
        c = run.curve_set.column(vb)
        np.testing.assert_allclose(
            run.curve_set.C[:, c], client[f"c_{vb}"].to_numpy(dtype=float), rtol=tol[str(vb)], atol=0,
            err_msg=f"curve VB{vb}",
        )
    # parity bounds: VALUATION_CALC k=0 data; parameters = LM fit of that grid (VB11: rolling k=1 fit). The
    # sheet used Solver, so the fitted parity differs by Solver convergence (VB22: a Solver local optimum, 1.4%).
    ub_tol = expected["pipeline_parity_ub_max_rel_tol"]
    report = {}
    for vb in VBS:
        c = run.curve_set.column(vb)
        want = client[f"ub_{vb}"].to_numpy(dtype=float)
        got = run.curve_set.UB[:, c]
        ok = ~np.isnan(want)
        np.testing.assert_array_equal(np.isnan(got), np.isnan(want), err_msg=f"UB blanks VB{vb}")
        rel = float(np.max(np.abs(got[ok] - want[ok]) / np.abs(want[ok])))
        report[vb] = rel
        assert rel <= ub_tol[str(vb)], f"UB VB{vb}: max rel {rel:.2e} > {ub_tol[str(vb)]}"
    print("parity UB vs Curves!H:M max rel diff: " + ", ".join(f"VB{vb} {r:.2e}" for vb, r in report.items()))
    b11 = run.bounds[11]
    assert b11.n_points == expected["valuation_cohort11"]["n"]


def test_parity_calc_fit_uses_the_sheets_truncated_sse_objective(fixtures_dir):
    """Cohort_44!B12 sums t <= 48 of 49 kept points (Q22); the parity calc fit must minimise that objective."""
    inputs = load_inputs_from_fixtures(fixtures_dir)
    run = run_curves(inputs, parity_jul26(), D, modes=("THREE_PARAM",))
    for vb in VBS:
        p = pd.read_parquet(fixtures_dir / "valuation" / f"cohort_{vb}_panel.parquet").set_index(["row", "col"])
        s_wb, cn_wb = (float(p.loc[(r, "B"), "value_num"]) for r in (5, 6))
        f = run.calc_fits[("THREE_PARAM", vb)]
        if vb in (11, 22):
            continue  # VB11: the sheet holds the rolling k=1 fit (override); VB22: a Solver local optimum
        tol = 5e-5 if vb == 44 else 2e-3  # VB44 pins the truncated objective; the rest is Solver-vs-LM noise
        assert abs(f.s - s_wb) < tol and abs(f.cn - cn_wb) < tol, (vb, f.s, s_wb, f.cn, cn_wb)

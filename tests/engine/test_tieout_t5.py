from datetime import date

import numpy as np
import pandas as pd
import pytest

from nutun_engine.config import parity_jul26
from nutun_engine.fit import fit_grid
from nutun_engine.grids import build_rolling_grids
from nutun_engine.inputs import load_inputs_from_fixtures
from nutun_engine.prepare import prepare_rolling

pytestmark = pytest.mark.tieout
D = date(2026, 7, 1)


@pytest.fixture(scope="module")
def grids(fixtures_dir):
    inputs = load_inputs_from_fixtures(fixtures_dir)
    cfg = parity_jul26()
    return build_rolling_grids(prepare_rolling(inputs, cfg, D), cfg, D)


def _params(fixtures_dir, wb):
    p = pd.read_parquet(fixtures_dir / wb / "Params.parquet")
    return {(int(r.k), int(r.vb)): r for r in p.itertuples()}


def test_t5b_three_param_lm_matches_solver_params(fixtures_dir, grids, expected):
    cfg = parity_jul26()
    wb = _params(fixtures_dir, "rolling_3p")
    worst = 0.0
    for g in grids:
        for r in fit_grid(g, cfg, "THREE_PARAM", cfg.fixed_mu_lookup()):
            w = wb[(r.k, r.vb)]
            assert r.status == "OK", (r.k, r.vb, r.reason)
            assert r.sse <= w.sse * (1 + 1e-6), (r.k, r.vb, r.sse, w.sse)
            if (r.k, r.vb) != (7, 23):  # ill-conditioned block: SSE test only (§16.2)
                assert abs(r.m - w.m) <= 1e-4 and abs(r.s - w.s) <= 1e-4 and abs(r.cn - w.cn) <= 1e-4, (r.k, r.vb, r.m, w.m, r.s, w.s, r.cn, w.cn)
                worst = max(worst, abs(r.m - w.m), abs(r.s - w.s), abs(r.cn - w.cn))
            assert r.K == int(w.K) and r.sum_count == int(w.sum_count) and (r.contiguous == (w.contiguous == "YES"))
            assert r.p == int(w.p) and r.df == int(w.df)
    print(f"T5b worst |d param| = {worst:.2e}")
    k0 = {r.vb: r for r in fit_grid(grids[0], cfg, "THREE_PARAM", {})}
    for vb, (m, s, cn) in expected["rolling_3p_k0"].items():
        r = k0[int(vb)]
        assert abs(r.m - m) < 1e-4 and abs(r.s - s) < 1e-4 and abs(r.cn - cn) < 1e-4
    e = expected["rolling_k0_vb11_3p"]
    assert k0[11].sse <= e["sse"] * (1 + 1e-6)


def test_t5c_fixed_mu_lm_matches_2p_workbook(fixtures_dir, grids, expected):
    cfg = parity_jul26()
    wb = _params(fixtures_dir, "rolling_2p")
    for g in grids:
        for r in fit_grid(g, cfg, "TWO_PARAM_FIXED_MU", cfg.fixed_mu_lookup()):
            w = wb[(r.k, r.vb)]
            assert r.status == "OK" and r.m == pytest.approx(float(w.m), abs=1e-12), (r.k, r.vb)
            assert abs(r.s - w.s) <= 1e-6 and abs(r.cn - w.cn) <= 1e-6, (r.k, r.vb, r.s, w.s, r.cn, w.cn)
            assert r.sse <= w.sse * (1 + 1e-8), (r.k, r.vb)
            assert r.K == int(w.K) and r.p == int(w.p) and r.df == int(w.df)
            assert r.s_e == pytest.approx(float(w.s_e), rel=1e-6)
            assert r.lifetime == pytest.approx(float(w.lifetime), rel=1e-6)
            assert r.mode_t == pytest.approx(float(w.mode), rel=1e-6)  # derives from s (1e-6)
            assert (r.warn or "") == (w.warn if isinstance(w.warn, str) else "")
    e = expected["rolling_k0_vb11_2p"]
    r11 = next(r for r in fit_grid(grids[0], cfg, "TWO_PARAM_FIXED_MU", cfg.fixed_mu_lookup()) if r.vb == 11)
    assert abs(r11.s - e["s"]) <= 1e-6 and abs(r11.cn - e["cn"]) <= 1e-6 and r11.sse <= e["sse"] * (1 + 1e-8)


# ---------------------------------------------------------------------------------------------------------------
# T5a: MANUAL mode with the workbook parameters reproduces every Cohort block column (rolling and valuation)
# ---------------------------------------------------------------------------------------------------------------
from nutun_engine.bounds import prediction_limits, sensitivity  # noqa: E402
from nutun_engine.fit import fit_block  # noqa: E402
from nutun_engine.grids import build_valuation_calc_grid  # noqa: E402
from nutun_engine.lognormal import curve  # noqa: E402
from nutun_engine.prepare import prepare_valuation_calc  # noqa: E402
from scripts.xlsx_stream import idx_to_col  # noqa: E402

VBS = (11, 15, 22, 23, 25, 44)
TABLE_COLS = ["w", "z", "phi", "pred", "resid", "x_m", "x_s", "x_cn", "h3", "h2", "h", "sqrt_term", "se_i", "half"]


def _panel(fixtures_dir, wb, name):
    p = pd.read_parquet(fixtures_dir / wb / name).set_index(["row", "col"])
    return lambda r, c: float(p.loc[(r, c), "value_num"])


def _close(a, b, label, rtol=1e-10):
    np.testing.assert_allclose(
        np.asarray(a, float), np.asarray(b, float), rtol=rtol, atol=1e-300, equal_nan=True, err_msg=label
    )


@pytest.mark.parametrize("wb", ["rolling_2p", "rolling_3p"])
def test_t5a_manual_params_reproduce_every_rolling_cohort_block(fixtures_dir, grids, wb):
    cfg = parity_jul26()
    for vb in VBS:
        for k in range(8):
            c0 = 1 + 24 * k
            val = idx_to_col(c0 + 1)
            mat = idx_to_col(c0 + 22)
            P = _panel(fixtures_dir, wb, f"cohort_{vb}_k{k}_panel.parquet")
            m, s, cn = P(3, val), P(4, val), P(5, val)
            g = grids[k]
            c = g.column(vb)
            fr = fit_block(g.t, g.constrained[:, c], g.keep[:, c], k=k, report_month=g.report_month, vb=vb,
                           mode="MANUAL", cfg=cfg, manual=(m, s, cn))
            label = f"{wb} VB{vb} k={k}"
            # VB23 k=7 is ill-conditioned (m 14.5, cn 22; det(V) tiny): the cofactor inverse amplifies
            # summation-order rounding to ~1e-10 in the leverage columns (§16.2 singles this block out)
            rt = 1e-8 if (k, vb) == (7, 23) else 1e-10
            assert fr.K == P(8, val) and fr.sum_count == P(10, val) and fr.p == P(12, val) and fr.df == P(13, val), label
            _close([fr.sse, fr.s_e, fr.mode_t, fr.lifetime], [P(11, val), P(14, val), P(17, val), P(18, val)], label)
            b = prediction_limits(g.t, g.constrained[:, c], g.keep[:, c], m, s, cn, alpha=cfg.curves.alpha, p=fr.p,
                                  points="KEPT", k=k, report_month=g.report_month, vb=vb)
            _close(b.t_mult, P(16, val), label + " t")
            _close([b.V[0, 0], b.V[0, 1], b.V[0, 2], b.V[1, 1], b.V[1, 2], b.V[2, 2], b.det_v],
                   [P(r, mat) for r in range(3, 10)], label + " V")
            _close([b.W[0, 0], b.W[0, 1], b.W[0, 2], b.W[1, 1], b.W[1, 2], b.W[2, 2]],
                   [P(r, mat) for r in range(10, 16)], label + " W", rt)
            _close([b.P[0, 0], b.P[0, 1], b.P[1, 1], b.det_p, b.Q[0, 0], b.Q[0, 1], b.Q[1, 1]],
                   [P(r, mat) for r in range(16, 23)], label + " P/Q", rt)
            tbl = pd.read_parquet(fixtures_dir / wb / f"cohort_{vb}_k{k}_table.parquet")
            assert tbl.t.tolist() == list(range(1, 61))
            np.testing.assert_array_equal(b.used, tbl.used.to_numpy() == 1, err_msg=label)
            for col in TABLE_COLS:
                _close(getattr(b, col), tbl[col].to_numpy(dtype=float), f"{label} {col}", rt)
            _close(b.lower, tbl.lower.to_numpy(dtype=float), f"{label} LOWER", rt)
            _close(b.upper, tbl.upper.to_numpy(dtype=float), f"{label} UPPER", rt)
            pred120 = pd.read_parquet(fixtures_dir / wb / f"cohort_{vb}_k{k}_pred120.parquet")
            _close(curve(np.arange(1.0, 121.0), m, s, cn), pred120.pred.to_numpy(dtype=float), f"{label} pred120")


def test_t5a_valuation_cohort_sheets_contiguous_prefix(fixtures_dir, expected):
    cfg = parity_jul26()
    mt, st, qt = cfg.bounds.matrix_t_max, cfg.bounds.sensitivity_t_max, cfg.bounds.sse_t_max  # Q22 per-sheet ranges
    inputs = load_inputs_from_fixtures(fixtures_dir)
    g = build_valuation_calc_grid(prepare_valuation_calc(inputs, cfg, D), cfg, D)
    for vb in VBS:
        P = _panel(fixtures_dir, "valuation", f"cohort_{vb}_panel.parquet")
        m, s, cn = P(4, "B"), P(5, "B"), P(6, "B")
        c = g.column(vb)
        tbl = pd.read_parquet(fixtures_dir / "valuation" / f"cohort_{vb}_table.parquet")
        obs = tbl.obs.to_numpy(dtype=float)  # t = 1..75; rows beyond the grid are NaN
        t = tbl.t.to_numpy(dtype=float)
        keep = np.zeros(len(t), bool)
        keep[:60] = g.keep[:, c]
        # the sheet's obs column is blank (not 0) beyond the kept prefix: compare where populated
        has = ~np.isnan(obs[:60])
        np.testing.assert_allclose(obs[:60][has], g.constrained[:, c][has], rtol=1e-12, atol=0)
        assert (g.constrained[:, c][~has] == 0).all()
        p = int(P(13, "J"))
        b = prediction_limits(t, obs, keep, m, s, cn, alpha=P(15, "B"), p=p, points="CONTIGUOUS_PREFIX",
                              report_month=D, vb=vb, matrix_t_max=mt[vb], sse_t_max=qt[vb])
        label = f"valuation VB{vb}"
        assert b.n_points == P(10, "B") and b.sum_count == P(11, "B") and b.df == P(14, "J"), label
        _close([b.sse, b.s_e, b.t_mult], [P(12, "B"), P(12, "J"), P(14, "B")], label)
        _close([b.V[0, 0], b.V[0, 1], b.V[0, 2], b.V[1, 1], b.V[1, 2], b.V[2, 2], b.det_v],
               [P(r, "AF") for r in range(5, 12)], label + " V")
        _close([b.W[0, 0], b.W[0, 1], b.W[0, 2], b.W[1, 1], b.W[1, 2], b.W[2, 2]],
               [P(r, "AF") for r in range(13, 19)], label + " W")
        _close([b.P[0, 0], b.P[0, 1], b.P[1, 1], b.det_p, b.Q[0, 0], b.Q[0, 1], b.Q[1, 1]],
               [P(r, "AF") for r in range(20, 27)], label + " P/Q")
        # rows beyond the kept prefix are empty cells in this sheet: compare the populated rows, and
        # require the engine's gated helper columns to be 0 there
        for col in TABLE_COLS:
            got = getattr(b, col)
            if col in ("z", "phi", "pred"):
                got = np.where(b.used, got, 0.0)  # columns N, O, P are gated on t ≤ n
            want = tbl[col].to_numpy(dtype=float)
            has = ~np.isnan(want)
            _close(got[has], want[has], f"{label} {col}")
            assert (got[~has] == 0).all(), f"{label} {col} not blank beyond the prefix"
        for col, got in (("lower", b.lower), ("upper", b.upper)):
            want = tbl[col].to_numpy(dtype=float)
            has = ~np.isnan(want)
            _close(got[has], want[has], f"{label} {col.upper()}")
            assert np.isnan(got[~has]).all(), f"{label} {col.upper()} not blank beyond the prefix"
        sens = sensitivity(t, obs, keep, m, s, cn, "CONTIGUOUS_PREFIX", t_max=st[vb])
        _close([sens[k2] for k2 in ("m-1%", "m+1%", "s-1%", "s+1%", "cn-1%", "cn+1%")],
               [P(r, "J") for r in range(4, 10)], label + " sensitivity")
    e = expected["valuation_cohort11"]
    P11 = _panel(fixtures_dir, "valuation", "cohort_11_panel.parquet")
    assert P11(13, "AF") == e["W11"] and P11(24, "AF") == e["Q22"]

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

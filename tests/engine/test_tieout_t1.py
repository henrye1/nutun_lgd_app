import numpy as np
import pytest

from api.info_query import info_summary
from nutun_engine.inputs import load_inputs_from_fixtures

pytestmark = pytest.mark.tieout


def test_t1_info_tab_totals_and_agreement_with_acm_vb_and_caeir(fixtures_dir):
    inp = load_inputs_from_fixtures(fixtures_dir)
    s = info_summary(inp.info)
    assert s["rows"] == 539
    assert round(s["sum_cost"], 2) == 8507208539.81
    assert s["pp_weighted_caeir"] == pytest.approx(0.2036773, abs=5e-8)
    m = inp.info.merge(inp.vb, on="wClientCode", how="outer", suffixes=("", "_vb"), indicator=True)
    assert (m["_merge"] == "both").all() and len(m) == 539
    np.testing.assert_array_equal(m.VB.to_numpy(), m.VB_vb.to_numpy())
    c = inp.info.merge(inp.caeir, on="wClientCode", how="inner", suffixes=("", "_c"))
    assert len(c) == 539
    np.testing.assert_allclose(c.CAEIR.to_numpy(), c.CAEIR_c.to_numpy(), rtol=0, atol=1e-12)
    np.testing.assert_allclose(c.Cost.to_numpy(), c.PP.to_numpy(), rtol=0, atol=0.005)

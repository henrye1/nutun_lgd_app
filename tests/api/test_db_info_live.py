from datetime import date

import pandas as pd
import pytest

from api.db import make_client_engine
from api.info_query import fetch_info, info_summary
from api.settings import Settings

pytestmark = [pytest.mark.db, pytest.mark.tieout]


def test_t1_fn_app_info_matches_info_tab_fixture(fixtures_dir, expected):
    engine = make_client_engine(Settings())
    live = fetch_info(engine, date(2026, 7, 1))
    s = info_summary(live)
    assert s["rows"] == expected["info_rows"] and round(s["sum_cost"], 2) == expected["info_sum_cost"]
    assert s["pp_weighted_caeir"] == pytest.approx(expected["info_pp_weighted_caeir"], abs=5e-8)
    fx = pd.read_parquet(fixtures_dir / "valuation" / "Info.parquet")
    fx["wClientCode"] = fx.wClientCode.astype("int64")
    m = live[["wClientCode", "VB", "Age", "CAEIR", "Cost"]].merge(fx, on="wClientCode", suffixes=("", "_wb"))
    assert len(m) == 539
    assert (m.VB == m.VB_wb).all() and (m.Age == m.Age_wb).all()
    assert (abs(m.CAEIR - m.CAEIR_wb) < 1e-12).all() and (abs(m.Cost.astype(float) - m.Cost_wb) < 0.005).all()

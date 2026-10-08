import numpy as np
import pandas as pd

from api.info_query import info_summary


def test_info_summary_weighted_caeir_and_counts():
    df = pd.DataFrame(
        {
            "wClientCode": [1, 2, 3],
            "VB": [11.0, np.nan, 15.0],
            "Age": [10, 20, 30],
            "CAEIR": [0.10, 0.30, np.nan],
            "Cost": [100.0, 300.0, 0.0],
        }
    )
    s = info_summary(df)
    assert s["rows"] == 3 and s["sum_cost"] == 400.0
    assert s["pp_weighted_caeir"] == (0.10 * 100 + 0.30 * 300) / 400
    assert s["books_without_vb"] == 1 and s["books_without_caeir"] == 1

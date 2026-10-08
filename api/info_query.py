"""The Info tab as a query (spec §4.3, Appendix A)."""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Engine, text

INFO_COLUMNS = ["wClientCode", "VB", "Age", "CAEIR", "Cost"]


def fetch_info(
    engine: Engine, report_month: date, extract_month: date | None = None, in_scope_only: bool = False
) -> pd.DataFrame:
    flag = "InScope" if in_scope_only else "HasInfoRow"
    sql = text(
        f"SELECT * FROM dbo.fn_APP_Info(:d, :x) WHERE {flag} = 1 "
        "ORDER BY CASE WHEN wClientCode < 999000000 THEN 0 ELSE 1 END, wClientCode"
    )
    with engine.connect() as cx:
        df = pd.read_sql(sql, cx, params={"d": report_month, "x": extract_month})
    df["wClientCode"] = df["wClientCode"].astype("int64")
    for c in ("CAEIR", "Cost", "PP_Alloc", "Face", "CollectedToDate"):
        if c in df:
            df[c] = df[c].astype("float64")
    return df


def info_summary(info: pd.DataFrame) -> dict:
    cost = info["Cost"].astype("float64")
    caeir = info["CAEIR"].astype("float64")
    w = cost.where(caeir.notna(), 0.0)
    weighted = float((caeir.fillna(0.0) * w).sum() / w.sum()) if w.sum() else None
    return {
        "rows": int(len(info)),
        "sum_cost": float(cost.sum()),
        "pp_weighted_caeir": weighted,
        "books_without_vb": int(info["VB"].isna().sum()),
        "books_without_caeir": int(caeir.isna().sum()),
    }

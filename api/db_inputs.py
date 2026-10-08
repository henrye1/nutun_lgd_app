"""RunInputs from the client database — read-only SELECTs over the §4.1 tables."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from nutun_engine.inputs import RunInputs, _canon

TABLE_SQL: dict[str, str] = {
    "payments": "SELECT wClientCode, CC, PaymentMonth, curPayment FROM dbo.ACM_Payments",
    "payments_vb44_excluded": (
        "SELECT wClientCode, CC, PaymentMonth, curPayment, Rows_Excluded, ReportingMonth, Reason "
        "FROM dbo.ACM_Payments_VB44_Excluded"
    ),
    "master": (
        "SELECT wClientCode, dtChargeOffDate, curOriginalCapital, curChargeOffAmount, curInterest, curLegalFees, "
        "dtLastPayment, naccounts, Code999, CustomerCode, Customers FROM dbo.ACM_Master"
    ),
    "universe": (
        "SELECT BookCode, Code999, CustomerCode, Customers, MasterRows, Accounts, Face, FirstChargeOff, LastPayment "
        "FROM dbo.ACM_Snap_BookUniverse"
    ),
    "vb": "SELECT wClientCode, VB FROM dbo.ACM_VB",
    "vb_alloc": "SELECT wClientCode, BookCode, VB, VB_raw, Face, PP FROM dbo.ACM_VB_Alloc",
    "caeir": "SELECT wClientCode, CAEIR, PP FROM dbo.ACM_CAEIR",
    "fli": "SELECT [Date], R2, Adj FROM dbo.ACM_FLI",
    "costs": "SELECT T, Cost FROM dbo.ACM_Costs",
    "costs_cohorts": "SELECT VB, T, Cost FROM dbo.ACM_Costs_Cohorts",
    "capping": "SELECT T, VB, LB, UB FROM dbo.ACM_Capping",
    "acm_config": "SELECT Name, Value FROM dbo.ACM_Config",
    "info": "SELECT wClientCode, VB, Age, CAEIR, Cost FROM dbo.fn_APP_Info(:d, NULL) WHERE HasInfoRow = 1",
}
_EMPTY_OVERRIDE = pd.DataFrame(
    {
        "wClientCode": pd.Series(dtype="int64"),
        "VB": pd.Series(dtype="float64"),
        "VB_raw": pd.Series(dtype="float64"),
    }
)


def read_vb_override_csv(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"VB override file not found: {p}")
    df = pd.read_csv(p)
    missing = {"wClientCode", "VB"} - set(df.columns)
    if missing:
        raise ValueError(f"VB override file lacks columns {sorted(missing)}")
    if "VB_raw" not in df:
        df["VB_raw"] = df["VB"]
    return df[["wClientCode", "VB", "VB_raw"]].astype({"wClientCode": "int64", "VB": "float64", "VB_raw": "float64"})


def load_inputs(
    fetch: Callable[[str, dict], pd.DataFrame], report_month: date, vb_override: pd.DataFrame | None = None
) -> RunInputs:
    frames = {}
    for key, sql in TABLE_SQL.items():
        params = {"d": report_month} if ":d" in sql else {}
        frames[key] = fetch(sql, params)
    cfg = frames.pop("acm_config")
    acm_config = {str(n): str(v) for n, v in zip(cfg["Name"], cfg["Value"])}
    canon = {k: _canon(k, v) for k, v in frames.items()}
    canon["vb_override"] = _canon("vb_override", vb_override if vb_override is not None else _EMPTY_OVERRIDE.copy())
    return RunInputs(**canon, acm_config=acm_config)


def load_inputs_from_db(engine: Engine, report_month: date, vb_override_csv: str = "") -> RunInputs:
    def fetch(sql: str, params: dict) -> pd.DataFrame:
        with engine.connect() as cx:
            return pd.read_sql(text(sql), cx, params=params or None)

    ov = read_vb_override_csv(vb_override_csv) if vb_override_csv else None
    return load_inputs(fetch, report_month, ov)

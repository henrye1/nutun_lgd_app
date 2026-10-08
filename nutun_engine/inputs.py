"""RunInputs: the immutable, canonicalised input tables of a run (spec §4.1, §5)."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from nutun_engine.dates import from_excel_serial


def code999(codes: pd.Series) -> pd.Series:
    """999-form: a negative code becomes 999 || ABS(code); a positive code is unchanged (spec §5)."""
    s = codes.astype("int64")
    neg = s < 0
    out = s.copy()
    out[neg] = ("999" + (-s[neg]).astype(str)).astype("int64")
    return out


def _coerce_dates(s: pd.Series) -> pd.Series:
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if s.dtype.kind in "iuf":
        ok = s.notna()
        out[ok] = pd.to_datetime([from_excel_serial(v) for v in s[ok]])
        return out
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.astype("datetime64[ns]")
    obj = s.astype("object")
    for i, v in obj.items():
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)) or v == "":
            continue
        if isinstance(v, (int, float)):
            out[i] = pd.Timestamp(from_excel_serial(v))
        elif isinstance(v, pd.Timestamp):
            out[i] = v
        else:
            out[i] = pd.Timestamp(str(v)[:10])
    return out


def to_date(s: pd.Series) -> pd.Series:
    return _coerce_dates(s)


def to_month(s: pd.Series) -> pd.Series:
    d = _coerce_dates(s)
    return d.dt.to_period("M").dt.to_timestamp()


def lookup_vb(code999_s: pd.Series, override: pd.DataFrame, source: pd.DataFrame) -> pd.Series:
    """VB_OVERRIDE first (a book listed there takes its override VB even when blank), then the source table."""
    ov = override.drop_duplicates("wClientCode").set_index("wClientCode")["VB"].astype("float64")
    src = source.drop_duplicates("wClientCode").set_index("wClientCode")["VB"].astype("float64")
    in_override = code999_s.isin(ov.index)
    return pd.Series(
        np.where(in_override, code999_s.map(ov), code999_s.map(src)), index=code999_s.index, dtype="float64"
    )


@dataclass(frozen=True)
class RunInputs:
    payments: pd.DataFrame  # wClientCode:int64 (book), CC:int64, PaymentMonth:datetime64 (1st), curPayment
    payments_vb44_excluded: pd.DataFrame  # same + Rows_Excluded, ReportingMonth, Reason
    master: pd.DataFrame  # wClientCode, dtChargeOffDate (NaT ok), curOriginalCapital, …, Code999, CustomerCode
    universe: pd.DataFrame  # BookCode, Code999, CustomerCode, Face, FirstChargeOff
    vb: pd.DataFrame  # wClientCode:int64 (999), VB:float64
    vb_alloc: pd.DataFrame  # wClientCode:int64 (999), BookCode, VB, VB_raw, Face, PP
    caeir: pd.DataFrame  # wClientCode:int64 (999), CAEIR, PP
    fli: pd.DataFrame  # Date:datetime64 (1st), R2, Adj
    costs: pd.DataFrame  # T, Cost
    costs_cohorts: pd.DataFrame  # VB, T, Cost
    capping: pd.DataFrame  # T, VB, LB, UB
    info: pd.DataFrame  # wClientCode:int64 (999), VB, Age, CAEIR, Cost
    vb_override: pd.DataFrame  # wClientCode:int64 (999), VB, VB_raw
    acm_config: dict[str, str]


_INT = {
    "payments": ["wClientCode", "CC"],
    "payments_vb44_excluded": ["wClientCode", "CC"],
    "master": ["wClientCode", "Code999", "CustomerCode"],
    "universe": ["BookCode", "Code999", "CustomerCode"],
    "vb": ["wClientCode"],
    "vb_alloc": ["wClientCode", "BookCode"],
    "caeir": ["wClientCode"],
    "info": ["wClientCode"],
    "vb_override": ["wClientCode"],
}
_MONTH = {"payments": ["PaymentMonth"], "payments_vb44_excluded": ["PaymentMonth", "ReportingMonth"], "fli": ["Date"]}
_DATE = {"master": ["dtChargeOffDate", "dtLastPayment"], "universe": ["FirstChargeOff", "LastPayment"]}


def _canon(name: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in _INT.get(name, []):
        if c in df:
            df[c] = df[c].astype("float64").astype("int64")
    for c in _MONTH.get(name, []):
        if c in df:
            df[c] = to_month(df[c])
    for c in _DATE.get(name, []):
        if c in df:
            df[c] = to_date(df[c])
    return df.reset_index(drop=True)


_FIXTURE_FILES = {
    "payments": "ACM_Payments",
    "payments_vb44_excluded": "ACM_Payments_VB44_Excluded",
    "master": "ACM_Master",
    "universe": "ACM_Snap_BookUniverse",
    "vb": "ACM_VB",
    "vb_alloc": "ACM_VB_Alloc",
    "caeir": "ACM_CAEIR",
    "fli": "ACM_FLI",
    "costs": "ACM_Costs",
    "costs_cohorts": "ACM_Costs_Cohorts",
    "capping": "ACM_Capping",
    "info": "Info",
    "vb_override": "VB_OVERRIDE",
}


def _fmt(v) -> str:
    """ACM_Config values as the workbook shows them: 12 not 12.0, 0.43, '2025-10'."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else str(v)


def load_inputs_from_fixtures(fixtures_dir: Path) -> RunInputs:
    base = Path(fixtures_dir) / "valuation"
    frames = {k: _canon(k, pd.read_parquet(base / f"{v}.parquet")) for k, v in _FIXTURE_FILES.items()}
    cfg = pd.read_parquet(base / "ACM_Config.parquet")
    acm_config = {str(n): _fmt(v) for n, v in zip(cfg["Name"], cfg["Value"])}
    return RunInputs(**frames, acm_config=acm_config)


def validate_inputs(inputs: RunInputs) -> list[str]:
    w: list[str] = []
    pm = inputs.payments.PaymentMonth
    if (pm.dt.day != 1).any():
        w.append(f"{int((pm.dt.day != 1).sum())} payment rows are not dated the first of the month")
    if inputs.fli.Date.duplicated().any():
        w.append("ACM_FLI has duplicate Date rows")
    for name, key in (
        ("vb", ["wClientCode"]),
        ("caeir", ["wClientCode"]),
        ("capping", ["VB", "T"]),
        ("vb_alloc", ["wClientCode"]),
    ):
        if getattr(inputs, name).duplicated(key).any():
            w.append(f"{name} has duplicate keys {key}")
    missing = sorted(set(inputs.payments.wClientCode) - set(inputs.master.wClientCode))
    if missing:
        w.append(f"{len(missing)} payment books have no ACM_Master row: {missing[:10]}")
    return w


def input_fingerprint(inputs: RunInputs) -> dict[str, dict]:
    """Row count, numeric sum and max date per table (spec §4.2). Hashing is added with the run store."""
    out = {}
    for f in fields(inputs):
        if f.name == "acm_config":
            continue
        df: pd.DataFrame = getattr(inputs, f.name)
        num = df.select_dtypes("number")
        dates = df.select_dtypes("datetime")
        has_dates = len(dates.columns) and dates.notna().any().any()
        out[f.name] = {
            "rows": int(len(df)),
            "sum": float(num.iloc[:, -1].sum()) if len(num.columns) else None,
            "max_date": str(dates.max().max().date()) if has_dates else None,
        }
    return out

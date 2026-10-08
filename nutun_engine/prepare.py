"""Payment preparation (spec §7.2). Two rule sets: VALUATION_CALC (ACM_Payments_Calc) and ROLLING (Tranche_Keys)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from nutun_engine.config import RunConfig
from nutun_engine.dates import edate, month_index_s
from nutun_engine.inputs import RunInputs, code999, lookup_vb

CALC_COLUMNS = [
    "wClientCode", "CC", "PaymentMonth", "curPayment", "Code999", "CC999", "VB", "ChargeOff", "MaxDate",
    "AgeCO", "Count", "R2", "FLIadj", "Face", "MaxCount", "Excl", "Include",
]


@dataclass(frozen=True)
class PrepResult:
    rows: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def fli_r2_series(fli: pd.DataFrame) -> pd.Series:
    return fli.drop_duplicates("Date").set_index("Date")["R2"].astype("float64")


def _payments_to(inputs: RunInputs, report_month: date) -> pd.DataFrame:
    pay = inputs.payments.loc[inputs.payments.PaymentMonth <= pd.Timestamp(report_month)]
    return pay.sort_values(["wClientCode", "PaymentMonth"], kind="stable").reset_index(drop=True)


def _master_first(inputs: RunInputs) -> pd.DataFrame:
    """VLOOKUP semantics: the first ACM_Master row per book code."""
    return inputs.master.drop_duplicates("wClientCode", keep="first").set_index("wClientCode")


def _r2(months: pd.Series, inputs: RunInputs, cfg: RunConfig, missing_rule: str) -> pd.Series:
    r2 = months.map(fli_r2_series(inputs.fli)).astype("float64")
    if missing_rule == "ONE":
        r2 = r2.fillna(1.0)
    if cfg.fli.r2_zero == "ONE":
        r2 = r2.where(r2 != 0.0, 1.0)
    return r2


def prepare_valuation_calc(inputs: RunInputs, cfg: RunConfig, report_month: date) -> PrepResult:
    warnings: list[str] = []
    pay = _payments_to(inputs, report_month)
    master = _master_first(inputs)
    df = pay[["wClientCode", "CC", "PaymentMonth", "curPayment"]].copy()
    df["Code999"] = code999(df.wClientCode)
    df["CC999"] = code999(df.CC)
    df["VB"] = lookup_vb(df.Code999, inputs.vb_override, inputs.vb_alloc[["wClientCode", "VB"]])
    df["ChargeOff"] = df.wClientCode.map(master["dtChargeOffDate"]).astype("datetime64[ns]")
    max_date = edate(pay.PaymentMonth.max().date(), cfg.curves.calc_offset) if len(pay) else report_month
    df["MaxDate"] = pd.Series(pd.Timestamp(max_date), index=df.index, dtype="datetime64[ns]")
    df["AgeCO"] = (month_index_s(df.MaxDate) - month_index_s(df.ChargeOff)) + 1.0  # Calc!M
    seq = (df.groupby("wClientCode").cumcount() + 1).astype("int64")
    over = (seq > df.AgeCO).fillna(False)
    df["Count"] = np.where(over, 999, seq).astype("int64")  # Calc!N
    df["R2"] = _r2(df.PaymentMonth, inputs, cfg, cfg.fli.missing_hist_month_calc)  # Calc!O
    df["FLIadj"] = df.curPayment * df.R2  # Calc!P
    df["Face"] = df.wClientCode.map(master["curOriginalCapital"]).astype("float64")  # Calc!Q
    valid = df.loc[df.Count != 999].groupby("wClientCode").Count.max()
    df["MaxCount"] = df.wClientCode.map(valid).fillna(0).astype("int64")  # Calc!R (MAXIFS → 0)
    no_master = df.AgeCO.isna()
    df["Excl"] = ((df.AgeCO <= 0) | (df.Count == 999) | no_master).astype(bool)  # Calc!S
    include = (~df.Excl) & (df.MaxCount >= 0)
    include &= ~((df.VB == 25) & (df.AgeCO <= cfg.curves.vb25_young_age_excl))
    include &= df.AgeCO <= cfg.curves.ndata
    if cfg.payments.exclusion_applied:  # Calc!T (inert in parity)
        include &= ~df.CC999.isin(cfg.payments.exclusion_list)
    df["Include"] = include.fillna(False).astype(bool)
    if no_master.any():
        books = sorted(df.loc[no_master, "wClientCode"].unique().tolist())
        warnings.append(f"{len(books)} payment books have no ACM_Master row and were excluded: {books[:10]}")
    return PrepResult(df[CALC_COLUMNS], warnings)

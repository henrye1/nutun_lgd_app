"""Payment preparation (spec §7.2). Two rule sets: VALUATION_CALC (ACM_Payments_Calc) and ROLLING (Tranche_Keys)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from nutun_engine.config import RunConfig
from nutun_engine.dates import datedif_m, edate, eomonth, month_index, month_index_s
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


ROLLING_TK_COLUMNS = [
    "wClientCode", "MaxPaymentMonth", "Code999", "VB", "ChargeOffDate", "Face", "CC", "CC999", "ExclOK",
    "Age_at_k0", "kmin",
]
ROLLING_PAY_COLUMNS = [
    "wClientCode", "CC", "PaymentMonth", "curPayment", "VB", "Count", "R2", "FLIadj", "balance", "kmin", "kmax",
]


@dataclass(frozen=True)
class RollingPrep:
    payments: pd.DataFrame
    tranche_keys: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


def _age_at_k0(chargeoff: pd.Series, anchor: date) -> pd.Series:
    """Tranche_Keys!J: DATEDIF(EOMONTH(co,0), EOMONTH(anchor,0), "m") + 1; blank when no charge-off."""
    end = eomonth(anchor)
    out = []
    for v in chargeoff:
        if pd.isna(v):
            out.append(np.nan)
            continue
        co = eomonth(pd.Timestamp(v).date())
        if co <= end:
            out.append(float(datedif_m(co, end) + 1))
        else:  # charged off after the anchor (historical run): plain month difference, ≤ 0
            out.append(float(month_index(end) - month_index(co) + 1))
    return pd.Series(out, index=chargeoff.index, dtype="float64")


def prepare_rolling(inputs: RunInputs, cfg: RunConfig, report_month: date) -> RollingPrep:
    warnings: list[str] = []
    pay = _payments_to(inputs, report_month)
    master = _master_first(inputs)
    anchor = report_month  # Cfg_MaxMonth = latest payment month in data = D for the parity run

    tk = pay.groupby("wClientCode", sort=True).PaymentMonth.max().rename("MaxPaymentMonth").reset_index()
    tk["MaxPaymentMonth"] = tk.MaxPaymentMonth.astype("datetime64[ns]")
    tk["Code999"] = code999(tk.wClientCode)
    tk["VB"] = lookup_vb(tk.Code999, inputs.vb_override, inputs.vb[["wClientCode", "VB"]])
    tk["ChargeOffDate"] = tk.wClientCode.map(master["dtChargeOffDate"]).astype("datetime64[ns]")
    tk["Face"] = tk.wClientCode.map(inputs.master.groupby("wClientCode").curOriginalCapital.sum()).fillna(0.0)
    tk["CC"] = tk.wClientCode.map(master["CustomerCode"]).astype("float64")
    cc_ok = tk.CC.notna()
    tk["CC999"] = pd.Series(np.nan, index=tk.index, dtype="float64")
    tk.loc[cc_ok, "CC999"] = code999(tk.loc[cc_ok, "CC"]).astype("float64")
    if cfg.payments.exclusion_applied_rolling:  # Tranche_Keys!I: live in the July-26 workbooks (see config)
        tk["ExclOK"] = (~tk.CC999.isin(cfg.payments.exclusion_list)).astype("int64")
    else:
        tk["ExclOK"] = 1
    tk["Age_at_k0"] = _age_at_k0(tk.ChargeOffDate, anchor)
    max_age = np.where(tk.VB == 44, cfg.curves.max_age_vb44, cfg.curves.max_age)
    kmin = np.maximum(0.0, tk.Age_at_k0 - max_age)
    tk["kmin"] = np.where(tk.ExclOK == 0, 9999.0, kmin).astype("float64")
    if tk.ChargeOffDate.isna().any():
        books = sorted(tk.loc[tk.ChargeOffDate.isna(), "wClientCode"].tolist())
        warnings.append(
            f"{len(books)} tranches have no charge-off date (kmin blank, excluded from every grid): {books[:10]}"
        )
    tk = tk[ROLLING_TK_COLUMNS]

    p = pay[["wClientCode", "CC", "PaymentMonth", "curPayment"]].merge(
        tk[["wClientCode", "VB", "Face", "kmin", "MaxPaymentMonth"]], on="wClientCode", how="left"
    )
    first = p.groupby("wClientCode").PaymentMonth.transform("min")
    p["Count"] = (month_index_s(p.PaymentMonth) - month_index_s(first) + 1).astype("int64")  # ACM_Payments!H
    p["R2"] = _r2(p.PaymentMonth, inputs, cfg, cfg.fli.missing_hist_month_rolling)  # ACM_Payments!I
    p["FLIadj"] = p.curPayment * p.R2  # ACM_Payments!J (NaN when R2 is blank)
    p["balance"] = p.Face.astype("float64")  # ACM_Payments!K
    if cfg.curves.offset_basis == "GLOBAL_CUTOFF":
        p["kmax"] = (month_index(report_month) - month_index_s(p.PaymentMonth)).astype("int64")
    else:  # ACM_Payments!M: DATEDIF to the tranche's own last payment month
        p["kmax"] = (month_index_s(p.MaxPaymentMonth) - month_index_s(p.PaymentMonth)).astype("int64")
    return RollingPrep(p[ROLLING_PAY_COLUMNS], tk, warnings)

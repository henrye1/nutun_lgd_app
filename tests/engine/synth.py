"""Small synthetic RunInputs for unit tests (public; no client data)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from nutun_engine.inputs import RunInputs, code999

VBS = (11, 15, 22, 23, 25, 44)


def make_inputs(payments, master, vb_alloc=None, vb=None, fli=None, vb_override=None, caeir=None) -> RunInputs:
    """payments: [(book_code, cc, month: date, amount)]
    master:   [(book_code, chargeoff: date | None, face, customer_code)]
    vb_alloc: [(code999, vb, face, pp)]         vb: [(code999, vb)]
    fli:      {month: (r2, adj)} — default: R2 = Adj = 1 for 2012-08 .. 2040-12
    vb_override: [(code999, vb)]               caeir: [(code999, caeir, pp)]
    """
    pay = pd.DataFrame(payments, columns=["wClientCode", "CC", "PaymentMonth", "curPayment"])
    pay["PaymentMonth"] = pd.to_datetime(pay["PaymentMonth"]).astype("datetime64[ns]")
    pay = pay.astype({"wClientCode": "int64", "CC": "int64", "curPayment": "float64"})

    m = pd.DataFrame(master, columns=["wClientCode", "dtChargeOffDate", "curOriginalCapital", "CustomerCode"])
    m["dtChargeOffDate"] = pd.to_datetime(m["dtChargeOffDate"]).astype("datetime64[ns]")
    m = m.astype({"wClientCode": "int64", "curOriginalCapital": "float64", "CustomerCode": "int64"})
    for c in ("curChargeOffAmount", "curInterest", "curLegalFees"):
        m[c] = 0.0
    m["naccounts"] = 1.0
    m["Code999"] = code999(m["wClientCode"])

    if vb_alloc is None:
        vb_alloc = [(int(c), 11, float(f), float(f) / 10) for c, f in zip(m["Code999"], m["curOriginalCapital"])]
    alloc = pd.DataFrame(vb_alloc, columns=["wClientCode", "VB", "Face", "PP"]).astype(
        {"wClientCode": "int64", "VB": "float64", "Face": "float64", "PP": "float64"}
    )
    alloc["BookCode"] = alloc["wClientCode"]
    alloc["VB_raw"] = alloc["VB"]

    vb_df = (
        pd.DataFrame(vb, columns=["wClientCode", "VB"]) if vb is not None else alloc[["wClientCode", "VB"]].copy()
    ).astype({"wClientCode": "int64", "VB": "float64"})

    if fli is None:
        months = pd.date_range("2012-08-01", "2040-12-01", freq="MS")
        fli_df = pd.DataFrame({"Date": months, "R2": 1.0, "Adj": 1.0})
    else:
        fli_df = pd.DataFrame(
            [(pd.Timestamp(k), v[0], v[1]) for k, v in fli.items()], columns=["Date", "R2", "Adj"]
        )
    fli_df = fli_df.astype({"Date": "datetime64[ns]", "R2": "float64", "Adj": "float64"})

    ov = pd.DataFrame(vb_override or [], columns=["wClientCode", "VB"]).astype(
        {"wClientCode": "int64", "VB": "float64"}
    )
    ov["VB_raw"] = ov["VB"]

    caeir_df = (
        pd.DataFrame(caeir, columns=["wClientCode", "CAEIR", "PP"])
        if caeir is not None
        else pd.DataFrame({"wClientCode": alloc.wClientCode, "CAEIR": 0.2, "PP": alloc.PP})
    ).astype({"wClientCode": "int64", "CAEIR": "float64", "PP": "float64"})

    universe = pd.DataFrame(
        {
            "BookCode": m.wClientCode,
            "Code999": m.Code999,
            "CustomerCode": m.CustomerCode,
            "Face": m.curOriginalCapital,
            "FirstChargeOff": m.dtChargeOffDate,
        }
    )
    info = pd.DataFrame(
        {"wClientCode": alloc.wClientCode, "VB": alloc.VB, "Age": np.nan, "CAEIR": 0.2, "Cost": alloc.PP}
    )
    costs = pd.DataFrame({"T": np.arange(1, 1001, dtype="float64"), "Cost": 0.05})
    costs_c = pd.DataFrame(
        [(v, t, 0.04) for v in (22, 44) for t in range(1, 1001)], columns=["VB", "T", "Cost"]
    ).astype("float64")
    capping = pd.DataFrame(
        [(t, v, 0.5, 1.5) for v in VBS for t in range(1, 13)], columns=["T", "VB", "LB", "UB"]
    ).astype("float64")
    excluded = pay.iloc[0:0].copy()
    return RunInputs(
        payments=pay,
        payments_vb44_excluded=excluded,
        master=m,
        universe=universe,
        vb=vb_df,
        vb_alloc=alloc,
        caeir=caeir_df,
        fli=fli_df,
        costs=costs,
        costs_cohorts=costs_c,
        capping=capping,
        info=info,
        vb_override=ov,
        acm_config={"AgeCapping": "12", "disc_time": "0.43", "MaxAgeDate": "60", "ndata": "60"},
    )

"""Excel-compatible date arithmetic (spec §3.2, §7 notation).

All month-level quantities in the engine are first-of-month dates or month indices.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd

_EXCEL_EPOCH = date(1899, 12, 30)  # Excel 1900 date system: serial 1 = 1900-01-01


def from_excel_serial(n: int | float) -> date:
    return _EXCEL_EPOCH + timedelta(days=int(n))


def to_excel_serial(d: date) -> int:
    return (d - _EXCEL_EPOCH).days


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def edate(d: date, n: int) -> date:
    """Excel EDATE: same day n months away, clamped to the target month's last day."""
    y, m0 = divmod(d.year * 12 + d.month - 1 + n, 12)
    m = m0 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def eomonth(d: date, n: int = 0) -> date:
    """Excel EOMONTH: last day of the month n months away."""
    e = edate(first_of_month(d), n)
    return e.replace(day=calendar.monthrange(e.year, e.month)[1])


def month_diff(a: date, b: date) -> int:
    """The workbook's (YEAR(b)−YEAR(a))*12 + (MONTH(b)−MONTH(a)). Day of month is ignored."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def datedif_m(a: date, b: date) -> int:
    """Excel DATEDIF(a, b, "m"): complete months, minus one when day(b) < day(a)."""
    if b < a:
        raise ValueError(f"DATEDIF: end {b} is before start {a}")
    m = month_diff(a, b)
    if b.day < a.day:
        m -= 1
    return m


def month_index(d: date) -> int:
    """year*12 + month − 1, so that differences of indices equal month_diff."""
    return d.year * 12 + d.month - 1


def month_index_s(s: pd.Series) -> pd.Series:
    """Vectorised month_index over a datetime64 Series. NaT → NaN (float64)."""
    return (s.dt.year * 12 + s.dt.month - 1).astype("float64")

from datetime import date

import pandas as pd
import pytest

from nutun_engine.dates import (
    datedif_m,
    edate,
    eomonth,
    first_of_month,
    from_excel_serial,
    month_diff,
    month_index,
    month_index_s,
    to_excel_serial,
)


def test_excel_serials_round_trip_known_workbook_values():
    assert from_excel_serial(46204) == date(2026, 7, 1)  # Example!D16
    assert from_excel_serial(45901) == date(2025, 9, 1)  # Example!B16 (backstop)
    assert from_excel_serial(41122) == date(2012, 8, 1)  # ACM_FLI first row
    assert from_excel_serial(41707) == date(2014, 3, 9)  # Tranche_Keys!E2
    assert from_excel_serial(49796) == date(2036, 5, 1)  # Example!C164
    assert to_excel_serial(date(2026, 7, 1)) == 46204
    assert from_excel_serial(46204.0) == date(2026, 7, 1)


def test_edate_matches_excel():
    assert edate(date(2026, 7, 1), -2) == date(2026, 5, 1)  # Example!C45 parity month
    assert edate(date(2026, 7, 1), 118) == date(2036, 5, 1)  # Example!C164
    assert edate(date(2026, 1, 31), 1) == date(2026, 2, 28)  # clamps to month end
    assert edate(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert edate(date(2026, 7, 1), 0) == date(2026, 7, 1)


def test_eomonth():
    assert eomonth(date(2026, 7, 15)) == date(2026, 7, 31)
    assert eomonth(date(2026, 1, 15), 1) == date(2026, 2, 28)
    assert eomonth(date(2026, 3, 31), -1) == date(2026, 2, 28)


def test_month_diff_is_year_month_arithmetic():
    assert month_diff(date(2014, 3, 9), date(2026, 7, 1)) == 148
    assert month_diff(date(2026, 7, 1), date(2026, 7, 1)) == 0
    assert month_diff(date(2026, 7, 1), date(2026, 5, 1)) == -2


def test_datedif_m_reproduces_tranche_keys_j2():
    # Tranche_Keys!J2 = DATEDIF(EOMONTH(2014-03-09,0), EOMONTH(2026-07-01,0), "m") + 1 = 149
    assert datedif_m(eomonth(date(2014, 3, 9)), eomonth(date(2026, 7, 1))) + 1 == 149


def test_datedif_m_loses_a_month_on_short_month_ends_q15():
    assert datedif_m(date(2026, 3, 31), date(2026, 4, 30)) == 0  # Excel gives 0, not 1
    assert datedif_m(date(2026, 1, 31), date(2026, 2, 28)) == 0
    assert datedif_m(date(2026, 1, 1), date(2026, 3, 1)) == 2
    assert datedif_m(date(2026, 1, 15), date(2026, 3, 14)) == 1
    with pytest.raises(ValueError):
        datedif_m(date(2026, 3, 1), date(2026, 2, 1))


def test_month_index():
    assert month_index(date(2026, 7, 1)) - month_index(date(2014, 3, 9)) == 148
    s = pd.Series(pd.to_datetime(["2026-07-01", None, "2012-08-01"]))
    out = month_index_s(s)
    assert out.iloc[0] == 2026 * 12 + 6
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == 2012 * 12 + 7


def test_first_of_month():
    assert first_of_month(date(2026, 7, 31)) == date(2026, 7, 1)

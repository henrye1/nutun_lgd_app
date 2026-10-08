import pandas as pd

from scripts.extract_fixtures import CellsSpec, TableSpec, extract_cells, extract_table
from scripts.xlsx_stream import XlsxStream
from tests.scripts.test_xlsx_stream import make_xlsx

SHEET = (
    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>'
    '<row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>2.5</v></c><c r="C2" t="s"><v>3</v></c></row>'
    '<row r="3"><c r="A3"><v>2</v></c><c r="B3" t="e"><v>#N/A</v></c><c r="C3" t="str"><v></v></c></row>'
    '<row r="4"><c r="A4"><v>3</v></c><c r="C4" t="s"><v>4</v></c></row>'
    '<row r="6"><c r="A6"><v>9</v></c></row>'
)
SHARED = ("id", "amount", "label", "x", "y")


def test_extract_table_uses_sheet_header_and_stops_at_blank_row(tmp_path):
    xs = XlsxStream(make_xlsx(tmp_path, SHEET, shared=SHARED))
    df, errors = extract_table(xs, TableSpec("t", "Sheet1", header_row=1, first_col="A", last_col="C"))
    assert list(df.columns) == ["id", "amount", "label"]
    assert len(df) == 3  # rows 2-4; row 5 is blank so row 6 is not read
    assert df["id"].dtype == "float64" and df["id"].tolist() == [1.0, 2.0, 3.0]
    assert df["amount"].dtype == "float64" and pd.isna(df["amount"].iloc[1])  # error → NaN
    assert errors == 1
    assert df["label"].dtype == "string" and df["label"].tolist()[0] == "x"
    assert pd.isna(df["label"].iloc[1])  # empty str result → missing


def test_extract_table_explicit_header_drops_underscore_columns(tmp_path):
    xs = XlsxStream(make_xlsx(tmp_path, SHEET, shared=SHARED))
    spec = TableSpec(
        "t", "Sheet1", header_row=1, first_col="A", last_col="C", last_row=3, header=("key", "_skip", "lbl")
    )
    df, _ = extract_table(xs, spec)
    assert list(df.columns) == ["key", "lbl"] and len(df) == 2


def test_extract_cells_long_format(tmp_path):
    xs = XlsxStream(make_xlsx(tmp_path, SHEET, shared=SHARED))
    df = extract_cells(xs, CellsSpec("c", "Sheet1", first_row=2, last_row=3, first_col="A", last_col="B"))
    assert list(df.columns) == ["row", "col", "value_num", "value_str"]
    ix = df.set_index(["row", "col"])
    assert ix.loc[(2, "B"), "value_num"] == 2.5
    assert ix.loc[(3, "B"), "value_str"] == "#N/A"

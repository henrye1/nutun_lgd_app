import zipfile

import pytest

from scripts.xlsx_stream import CellError, XlsxStream, col_to_idx, idx_to_col

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def make_xlsx(tmp_path, sheet_xml: str, shared=("hello",), name="Sheet1"):
    p = tmp_path / "t.xlsx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{NS_MAIN}" xmlns:r="{NS_R}"><sheets>'
            f'<sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{NS_PKG}"><Relationship Id="rId1" '
            f'Type="x" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{NS_MAIN}">' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>",
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{NS_MAIN}"><sheetData>{sheet_xml}</sheetData></worksheet>',
        )
    return p


SHEET = (
    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>1.5</v></c>'
    '<c r="C1" t="str"><f>"x"&amp;"y"</f><v>xy</v></c></row>'
    '<row r="2"><c r="A2"><f>1+1</f><v>2</v></c><c r="B2" t="e"><v>#N/A</v></c>'
    '<c r="D2" t="b"><v>1</v></c></row>'
    '<row r="4"><c r="A4"/><c r="B4" t="inlineStr"><is><t>inline</t></is></c></row>'
)


def test_col_index_conversion():
    assert col_to_idx("A") == 1 and col_to_idx("Z") == 26 and col_to_idx("AA") == 27 and col_to_idx("BM") == 65
    assert idx_to_col(1) == "A" and idx_to_col(27) == "AA" and idx_to_col(65) == "BM"


def test_reads_cached_values_shared_strings_errors_bools_inline(tmp_path):
    xs = XlsxStream(make_xlsx(tmp_path, SHEET))
    assert xs.sheets == {"Sheet1": "xl/worksheets/sheet1.xml"}
    rows = list(xs.iter_rows("Sheet1"))
    assert rows[0] == (1, {1: "hello", 2: 1.5, 3: "xy"})
    r2 = rows[1]
    assert r2[0] == 2 and r2[1][1] == 2.0 and r2[1][4] is True
    assert isinstance(r2[1][2], CellError) and r2[1][2] == "#N/A"
    assert rows[2] == (4, {2: "inline"})  # blank A4 omitted, row 3 absent


def test_row_and_column_windows(tmp_path):
    xs = XlsxStream(make_xlsx(tmp_path, SHEET))
    assert [r for r, _ in xs.iter_rows("Sheet1", first_row=2, last_row=2)] == [2]
    rows = list(xs.iter_rows("Sheet1", first_col=2, last_col=3))
    assert rows[0] == (1, {2: 1.5, 3: "xy"})


def test_unknown_sheet_raises(tmp_path):
    xs = XlsxStream(make_xlsx(tmp_path, SHEET))
    with pytest.raises(KeyError):
        list(xs.iter_rows("Nope"))

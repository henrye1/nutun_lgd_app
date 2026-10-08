"""Streaming reader of cached cell values from large .xlsx/.xlsm files (spec §16.1)."""
from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from lxml import etree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_CELL_RE = re.compile(r"([A-Z]+)(\d+)")


class CellError(str):
    """An Excel error value (#N/A, #DIV/0!, ...)."""


def col_to_idx(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def idx_to_col(i: int) -> str:
    out = ""
    while i > 0:
        i, rem = divmod(i - 1, 26)
        out = chr(65 + rem) + out
    return out


class XlsxStream:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.z = zipfile.ZipFile(self.path)
        self.sheets = self._sheet_parts()
        self.shared = self._shared_strings()

    def _sheet_parts(self) -> dict[str, str]:
        wb = etree.fromstring(self.z.read("xl/workbook.xml"))
        rels = etree.fromstring(self.z.read("xl/_rels/workbook.xml.rels"))
        rid = {r.get("Id"): r.get("Target") for r in rels.iter(NS_PKG + "Relationship")}
        out: dict[str, str] = {}
        for s in wb.iter(NS + "sheet"):
            target = rid[s.get(NS_R + "id")].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            out[s.get("name")] = target
        return out

    def _shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self.z.namelist():
            return []
        out: list[str] = []
        with self.z.open("xl/sharedStrings.xml") as fh:
            for _, si in etree.iterparse(fh, events=("end",), tag=NS + "si"):
                out.append("".join(t.text or "" for t in si.iter(NS + "t")))
                si.clear()
        return out

    def _value(self, c):
        t = c.get("t")
        if t == "inlineStr":
            s = "".join(x.text or "" for x in c.iter(NS + "t"))
            return s or None
        v = c.find(NS + "v")
        if v is None or v.text is None:
            return None
        if t == "s":
            return self.shared[int(v.text)]
        if t == "str":
            return v.text
        if t == "b":
            return v.text == "1"
        if t == "e":
            return CellError(v.text)
        return float(v.text)

    def iter_rows(
        self,
        sheet: str,
        first_row: int = 1,
        last_row: int | None = None,
        first_col: int = 1,
        last_col: int | None = None,
    ) -> Iterator[tuple[int, dict[int, object]]]:
        part = self.sheets[sheet]  # KeyError for an unknown sheet
        with self.z.open(part) as fh:
            for _, row in etree.iterparse(fh, events=("end",), tag=NS + "row"):
                r = int(row.get("r"))
                if last_row is not None and r > last_row:
                    row.clear()
                    break
                if r >= first_row:
                    cells: dict[int, object] = {}
                    for c in row.iter(NS + "c"):
                        m = _CELL_RE.match(c.get("r"))
                        ci = col_to_idx(m.group(1))
                        if ci < first_col or (last_col is not None and ci > last_col):
                            continue
                        val = self._value(c)
                        if val is not None:
                            cells[ci] = val
                    yield r, cells
                row.clear()
                while row.getprevious() is not None:
                    del row.getparent()[0]

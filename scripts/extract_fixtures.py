"""Extract cached workbook values into parquet fixtures (spec §16.1).

Usage:  uv run python -m scripts.extract_fixtures [--only valuation,rolling_2p] [--out tests/fixtures/private]
The reference workbooks are looked for in ./reference and then in the repo root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts.xlsx_stream import CellError, XlsxStream, col_to_idx, idx_to_col

ROOT = Path(__file__).resolve().parent.parent
VBS = (11, 15, 22, 23, 25, 44)


@dataclass(frozen=True)
class TableSpec:
    name: str
    sheet: str
    header_row: int
    first_col: str
    last_col: str
    last_row: int | None = None
    header: tuple[str, ...] | None = None


@dataclass(frozen=True)
class CellsSpec:
    name: str
    sheet: str
    first_row: int
    last_row: int
    first_col: str
    last_col: str


def _grid_header(prefixes: tuple[str, ...]) -> tuple[str, ...]:
    return ("t",) + tuple(f"{p}_{vb}" for p in prefixes for vb in VBS)


CALC_ROWS_HEADER = (
    "wClientCode", "CC", "PaymentMonth", "curPayment", "_E", "Code999_txt", "Code999", "CC999_txt", "CC999",
    "vb", "ChargeOff", "MaxDate", "AgeCO", "Count", "R2", "FLIadj", "Face", "MaxCount", "Excl", "Include",
)
ROLLING_PAY_HEADER = (
    "wClientCode", "CC", "PaymentMonth", "curPayment", "_E", "TIdx", "vb", "Count", "R2", "FLIadj", "balance",
    "kmin", "kmax",
)
PARAMS_HEADER = (
    "k", "report_month", "vb", "m", "s", "cn", "mbound", "m_at_bound", "K", "contiguous", "sum_count", "sse",
    "p", "df", "s_e", "mode", "lifetime", "rule4", "warn", "fit_sheet",
)
CURVES_HEADER = (
    ("t",)
    + tuple(f"c_{vb}" for vb in VBS)
    + tuple(f"ub_{vb}" for vb in VBS)
    + tuple(f"lb_{vb}" for vb in VBS)
)

ACM_TABLES = [
    "ACM_Payments", "ACM_Payments_VB44_Excluded", "ACM_Master", "ACM_Snap_BookUniverse", "ACM_VB",
    "ACM_VB_Alloc", "ACM_CAEIR", "ACM_FLI", "ACM_Costs", "ACM_Costs_Cohorts", "ACM_Capping", "ACM_Config",
]

VALUATION_SPECS: list[TableSpec | CellsSpec] = [
    *[TableSpec(t, t, 1, "A", "O") for t in ACM_TABLES],
    TableSpec("Info", "Info", 3, "A", "E"),
    TableSpec("VB_OVERRIDE", "VB_OVERRIDE", 1, "A", "C", header=("wClientCode", "VB", "VB_raw")),
    TableSpec("calc_rows", "ACM_Payments_Calc", 1, "A", "T", header=CALC_ROWS_HEADER),
    TableSpec(
        "calc_grid", "ACM_Payments_Calc", 2, "W", "BM", last_row=62,
        header=_grid_header(("pay", "bal", "yld", "nho", "bal2", "keep", "cy")),
    ),
    CellsSpec("calc_constants", "ACM_Payments_Calc", 2, 10, "BO", "BQ"),
    TableSpec("Curves", "Curves", 3, "A", "S", last_row=503, header=CURVES_HEADER),
    CellsSpec("Config_Claude", "Config_Claude", 1, 20, "A", "C"),
]

ROLLING_SPECS: list[TableSpec | CellsSpec] = [
    TableSpec("ACM_Payments", "ACM_Payments", 1, "A", "M", header=ROLLING_PAY_HEADER),
    TableSpec("Tranche_Keys", "Tranche_Keys", 1, "A", "K"),
    TableSpec("ACM_Master", "ACM_Master", 1, "A", "O"),
    TableSpec("ACM_VB", "ACM_VB", 1, "A", "B"),
    TableSpec("ACM_FLI", "ACM_FLI", 1, "A", "C"),
    TableSpec("VB_OVERRIDE", "VB_OVERRIDE", 1, "A", "C", header=("wClientCode", "VB", "VB_raw")),
    *[
        TableSpec(
            f"Yields_M{k}", f"Yields_M{k}", 6, "A", "AK", last_row=66,
            header=_grid_header(("pay", "bal", "yld", "nho", "keep", "cy")),
        )
        for k in range(8)
    ],
    TableSpec("Params", "Params", 4, "A", "T", last_row=52, header=PARAMS_HEADER),
    CellsSpec("Config", "Config", 3, 27, "A", "I"),
]

REGISTRY: dict[str, tuple[str, list[TableSpec | CellsSpec]]] = {
    "valuation": ("*July2026_Nutun_Curves.xlsm", VALUATION_SPECS),
    "rolling_2p": ("*Danielle_2Param_Replicate.xlsm", ROLLING_SPECS),
    "rolling_3p": ("*Danielle_Replicate.xlsm", ROLLING_SPECS),
}


def _column(values: list) -> pd.Series:
    vals = [None if isinstance(v, CellError) or v == "" else v for v in values]
    nonnull = [v for v in vals if v is not None]
    if nonnull and all(isinstance(v, float) for v in nonnull):
        return pd.Series(vals, dtype="float64")
    if nonnull and all(isinstance(v, bool) for v in nonnull):
        return pd.Series(vals, dtype="boolean")
    return pd.Series([None if v is None else str(v) for v in vals], dtype="string")


def extract_table(xs: XlsxStream, spec: TableSpec) -> tuple[pd.DataFrame, int]:
    c0, c1 = col_to_idx(spec.first_col), col_to_idx(spec.last_col)
    ncol = c1 - c0 + 1
    rows = xs.iter_rows(spec.sheet, first_row=spec.header_row, last_row=spec.last_row, first_col=c0, last_col=c1)
    header: list[str] | None = list(spec.header) if spec.header else None
    data: list[list[object]] = []
    errors = 0
    expected_row = spec.header_row + 1
    for r, cells in rows:
        if r == spec.header_row:
            if header is None:
                header = [str(cells.get(c0 + i, f"col_{idx_to_col(c0 + i)}")) for i in range(ncol)]
            continue
        if r != expected_row or c0 not in cells:
            break  # a skipped row number or a blank key cell (first column) ends the table
        expected_row += 1
        row = [cells.get(c0 + i) for i in range(ncol)]
        errors += sum(isinstance(v, CellError) for v in row)
        data.append(row)
    if header is None:
        raise ValueError(f"{spec.sheet}: header row {spec.header_row} not found")
    if len(header) != ncol:
        raise ValueError(f"{spec.name}: header has {len(header)} names for {ncol} columns")
    cols = {name: _column([row[i] for row in data]) for i, name in enumerate(header) if not name.startswith("_")}
    return pd.DataFrame(cols), errors


def extract_cells(xs: XlsxStream, spec: CellsSpec) -> pd.DataFrame:
    c0, c1 = col_to_idx(spec.first_col), col_to_idx(spec.last_col)
    recs = []
    for r, cells in xs.iter_rows(spec.sheet, spec.first_row, spec.last_row, c0, c1):
        for ci, v in cells.items():
            num = v if isinstance(v, float) and not isinstance(v, bool) else None
            recs.append({"row": r, "col": idx_to_col(ci), "value_num": num, "value_str": str(v)})
    return pd.DataFrame(recs, columns=["row", "col", "value_num", "value_str"]).astype(
        {"row": "int64", "col": "string", "value_num": "float64", "value_str": "string"}
    )


def _find_workbook(reference_dirs: list[Path], pattern: str) -> Path:
    for d in reference_dirs:
        hits = sorted(d.glob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"no workbook matching {pattern} in {reference_dirs}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_all(reference_dirs: list[Path], out_dir: Path, only: set[str] | None = None) -> dict:
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for key, (pattern, specs) in REGISTRY.items():
        if only and key not in only:
            continue
        wb = _find_workbook(reference_dirs, pattern)
        xs = XlsxStream(wb)
        entry = {"source": wb.name, "sha256": _sha256(wb), "tables": {}}
        (out_dir / key).mkdir(parents=True, exist_ok=True)
        for spec in specs:
            if isinstance(spec, TableSpec):
                df, errors = extract_table(xs, spec)
            else:
                df, errors = extract_cells(xs, spec), 0
            df.to_parquet(out_dir / key / f"{spec.name}.parquet", index=False)
            entry["tables"][spec.name] = {"rows": int(len(df)), "cols": list(df.columns), "errors": errors}
            print(f"{key}/{spec.name}: {len(df)} rows, {errors} error cells")
        manifest[key] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "tests" / "fixtures" / "private"))
    ap.add_argument("--only", default=None, help="comma-separated registry keys")
    ap.add_argument("--reference-dir", action="append", default=None)
    a = ap.parse_args(argv)
    dirs = [Path(d) for d in a.reference_dir] if a.reference_dir else [ROOT / "reference", ROOT]
    extract_all(dirs, Path(a.out), set(a.only.split(",")) if a.only else None)


if __name__ == "__main__":
    main()

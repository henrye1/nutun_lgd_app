"""Required client objects and their health check (spec §4.1, §10.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy import Engine, text

Kind = Literal["table", "function"]


@dataclass(frozen=True)
class RequiredObject:
    name: str
    kind: Kind
    columns: tuple[str, ...]
    sql_file: str | None = None


REQUIRED_OBJECTS: list[RequiredObject] = [
    RequiredObject("ACM_Payments", "table", ("wClientCode", "CC", "PaymentMonth", "curPayment")),
    RequiredObject(
        "ACM_Payments_VB44_Excluded", "table",
        ("wClientCode", "CC", "PaymentMonth", "curPayment", "Rows_Excluded", "ReportingMonth", "Reason"),
    ),
    RequiredObject(
        "ACM_Master", "table",
        ("wClientCode", "dtChargeOffDate", "curOriginalCapital", "curChargeOffAmount", "curInterest",
         "curLegalFees", "dtLastPayment", "naccounts", "Code999", "CustomerCode", "Customers"),
    ),
    RequiredObject(
        "ACM_Snap_BookUniverse", "table",
        ("BookCode", "Code999", "CustomerCode", "Customers", "MasterRows", "Accounts", "Face", "FirstChargeOff",
         "LastPayment"),
    ),
    RequiredObject("ACM_VB", "table", ("wClientCode", "VB")),
    RequiredObject(
        "ACM_VB_Alloc", "table",
        ("wClientCode", "BookCode", "VB", "VB_raw", "QualityBand", "SectorCode", "Final_Sector2", "Face", "PP", "cR"),
    ),
    RequiredObject("ACM_CAEIR", "table", ("wClientCode", "CAEIR", "PP")),
    RequiredObject("ACM_FLI", "table", ("Date", "R2", "Adj")),
    RequiredObject("ACM_Costs", "table", ("T", "Cost")),
    RequiredObject("ACM_Costs_Cohorts", "table", ("VB", "T", "Cost")),
    RequiredObject("ACM_Capping", "table", ("T", "VB", "LB", "UB")),
    RequiredObject("ACM_Config", "table", ("Name", "Value")),
    RequiredObject(
        "fn_APP_Info", "function",
        ("wClientCode", "VB", "Age", "CAEIR", "Cost", "BookCode", "Age_Rolled", "Age_ChargeOff",
         "Age_FirstCollection", "ObservedMonths", "InScope", "HasInfoRow"),
        sql_file="sql/fn_APP_Info.sql",
    ),
]


@dataclass(frozen=True)
class ObjectInfo:
    name: str
    kind: str
    modify_date: datetime | None
    columns: list[str]


@dataclass
class ObjectStatus:
    name: str
    kind: str
    exists: bool
    row_count: int | None = None
    modify_date: datetime | None = None
    missing_columns: list[str] = field(default_factory=list)
    ok: bool = False
    hint: str = ""


class Catalog(Protocol):
    def object_info(self, name: str) -> ObjectInfo | None: ...

    def row_count(self, name: str, kind: Kind) -> int | None: ...


class SqlServerCatalog:
    def __init__(self, engine: Engine):
        self.engine = engine

    def object_info(self, name: str) -> ObjectInfo | None:
        with self.engine.connect() as cx:
            row = cx.execute(
                text(
                    "SELECT o.type_desc, o.modify_date FROM sys.objects o "
                    "WHERE o.schema_id = SCHEMA_ID('dbo') AND o.name = :n"
                ),
                {"n": name},
            ).first()
            if row is None:
                return None
            cols = [
                r[0]
                for r in cx.execute(
                    text("SELECT c.name FROM sys.columns c WHERE c.object_id = OBJECT_ID(:q) ORDER BY c.column_id"),
                    {"q": f"dbo.{name}"},
                )
            ]
        kind = "function" if "FUNCTION" in str(row[0]) else "table"
        return ObjectInfo(name, kind, row[1], cols)

    def row_count(self, name: str, kind: Kind) -> int | None:
        if not name.replace("_", "").isalnum():
            return None
        src = f"dbo.[{name}]" if kind == "table" else f"dbo.[{name}]('2026-07-01', NULL)"
        with self.engine.connect() as cx:
            return int(cx.execute(text(f"SELECT COUNT_BIG(*) FROM {src}")).scalar())


def check_objects(catalog: Catalog) -> list[ObjectStatus]:
    out = []
    for req in REQUIRED_OBJECTS:
        try:
            info = catalog.object_info(req.name)
        except Exception as exc:  # the database is down or refuses the login: say so, never 500
            out.append(ObjectStatus(req.name, req.kind, exists=False,
                                    hint=f"cannot check: {type(exc).__name__}: {str(exc)[:200]}"))
            continue
        if info is None:
            hint = f"Run {req.sql_file} in SSMS" if req.sql_file else "Run ACM_Pipeline_Simplified.sql to rebuild this table"
            out.append(ObjectStatus(req.name, req.kind, exists=False, hint=hint))
            continue
        missing = [c for c in req.columns if c not in info.columns]
        try:
            count = catalog.row_count(req.name, req.kind)
        except Exception as exc:
            count, missing = None, missing + [f"(count failed: {type(exc).__name__})"]
        ok = not missing
        hint = "" if ok else f"missing columns: {', '.join(missing)}"
        out.append(ObjectStatus(req.name, info.kind, True, count, info.modify_date, missing, ok, hint))
    return out

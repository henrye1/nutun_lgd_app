import re
from pathlib import Path

SQL = Path(__file__).resolve().parent.parent / "sql" / "fn_APP_Info.sql"


def test_sql_file_creates_only_the_info_function():
    text = SQL.read_text(encoding="utf-8")
    assert "CREATE OR ALTER FUNCTION dbo.fn_APP_Info" in text
    assert "RETURNS TABLE" in text
    # the app never ships DDL/DML against client tables (spec §0.2, §0.3)
    forbidden = re.compile(
        r"^\s*(CREATE\s+TABLE|DROP\s+|ALTER\s+TABLE|INSERT\s+|UPDATE\s+|DELETE\s+|TRUNCATE\s+)", re.I | re.M
    )
    assert forbidden.search(text) is None


def test_sql_file_checks_block_expects_539_rows():
    text = SQL.read_text(encoding="utf-8")
    assert "Info rows (expect 539)" in text
    assert "Sum Cost (compare with the Info tab total)" in text  # no client figure in the committed SQL

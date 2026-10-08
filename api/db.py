"""SQLAlchemy engine for the client database. Read-only by intent: the data layer only issues SELECT."""
from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, text

from api.settings import Settings


def make_client_engine(settings: Settings) -> Engine:
    url = "mssql+pyodbc:///?odbc_connect=" + quote_plus(settings.odbc_connect_string())
    return create_engine(url, pool_pre_ping=True, connect_args={"timeout": 5}, future=True)


def ping(engine: Engine) -> tuple[bool, str]:
    try:
        with engine.connect() as cx:
            cx.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:  # the driver message never carries the password
        return False, type(exc).__name__ + ": " + str(exc).split("\n")[0][:300]

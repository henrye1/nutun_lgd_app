from datetime import datetime

from fastapi.testclient import TestClient

from api.catalog import REQUIRED_OBJECTS, ObjectInfo
from api.deps import get_catalog, get_settings
from api.main import app
from api.settings import Settings
from tests.api.test_catalog import FakeCatalog


def _client(catalog=None, settings=None):
    app.dependency_overrides[get_settings] = lambda: settings or Settings(_env_file=None, db_server="h,1", db_name="d")
    if catalog is not None:
        app.dependency_overrides[get_catalog] = lambda: catalog
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health():
    r = _client().get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and "version" in r.json()


def test_db_status_reports_unreachable_without_500():
    s = Settings(_env_file=None, db_server="127.0.0.1,1", db_name="nope", db_driver="ODBC Driver 18 for SQL Server")
    r = _client(settings=s).get("/api/db/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True and body["reachable"] is False and body["error"]
    assert "password" not in body and body["server"] == "127.0.0.1,1"


def test_db_status_unconfigured(monkeypatch):
    monkeypatch.delenv("NUTUN_DB_SERVER", raising=False)
    r = _client(settings=Settings(_env_file=None)).get("/api/db/status")
    assert r.json() == {
        "configured": False, "server": "", "database": "", "auth": "windows", "reachable": False,
        "error": "NUTUN_DB_SERVER is not set",
    }


def test_db_objects_lists_every_required_object():
    objs = {o.name: ObjectInfo(o.name, o.kind, datetime(2026, 8, 1), list(o.columns)) for o in REQUIRED_OBJECTS}
    del objs["fn_APP_Info"]
    r = _client(catalog=FakeCatalog(objs, {o.name: 3 for o in REQUIRED_OBJECTS})).get("/api/db/objects")
    assert r.status_code == 200
    rows = {x["name"]: x for x in r.json()}
    assert len(rows) == len(REQUIRED_OBJECTS)
    assert rows["ACM_Payments"]["ok"] and rows["ACM_Payments"]["row_count"] == 3
    assert rows["ACM_Payments"]["modify_date"].startswith("2026-08-01")
    assert not rows["fn_APP_Info"]["ok"] and "fn_APP_Info.sql" in rows["fn_APP_Info"]["hint"]

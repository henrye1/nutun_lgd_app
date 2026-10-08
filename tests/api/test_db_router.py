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


def test_db_info_returns_503_when_query_fails():
    class BadEngine:
        def connect(self):
            raise RuntimeError("no driver")

    from api.deps import get_engine

    app.dependency_overrides[get_engine] = lambda: BadEngine()
    r = _client().get("/api/db/info", params={"report_month": "2026-07-01"})
    assert r.status_code == 503 and "Info query failed" in r.json()["detail"]


def test_db_objects_unconfigured_returns_503_not_local_instance(monkeypatch):
    monkeypatch.delenv("NUTUN_DB_SERVER", raising=False)
    r = _client(settings=Settings(_env_file=None)).get("/api/db/objects")
    assert r.status_code == 503 and "NUTUN_DB_SERVER" in r.json()["detail"]


def test_db_objects_unreachable_returns_statuses_with_hint():
    class DownCatalog:
        def object_info(self, name):
            raise RuntimeError("login timeout")

        def row_count(self, name, kind):
            raise RuntimeError("login timeout")

    r = _client(catalog=DownCatalog()).get("/api/db/objects")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == len(REQUIRED_OBJECTS)
    assert all(not x["ok"] and not x["exists"] and "cannot check" in x["hint"] and "login timeout" in x["hint"] for x in rows)


def test_spa_route_never_serves_files_outside_dist():
    import pytest

    from api.main import DIST

    if not DIST.exists():
        pytest.skip("web/dist not built")
    c = _client()
    r = c.get("/..%2F..%2F.env.example")
    assert r.status_code == 200 and "NUTUN_DB_SERVER" not in r.text and "<div id=\"root\">" in r.text
    r2 = c.get("/../../pyproject.toml")
    assert "hatchling" not in r2.text

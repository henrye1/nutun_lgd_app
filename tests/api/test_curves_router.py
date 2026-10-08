import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.runs import RUNS


def setup_function():
    RUNS.clear()
    app.dependency_overrides.clear()


def test_unknown_run_and_bad_preset():
    c = TestClient(app)
    assert c.get("/api/curves/nope/params").status_code == 404
    r = c.post("/api/curves/run", json={"report_month": "2026-07-01", "preset": "WRONG", "source": "fixtures"})
    assert r.status_code == 422


def test_manual_mode_is_rejected_and_engine_errors_are_not_500(monkeypatch):
    c = TestClient(app)
    r = c.post(
        "/api/curves/run",
        json={"report_month": "2026-07-01", "preset": "PARITY_JUL26", "source": "fixtures", "modes": ["MANUAL"]},
    )
    assert r.status_code == 422
    import api.routers.curves as mod

    def boom(*a, **k):
        raise ValueError("ma_missing = FAIL: VB23 k=4 not fittable")

    monkeypatch.setattr(mod, "run_curves", boom)
    monkeypatch.setattr(mod, "load_inputs_from_fixtures", lambda fx: object())
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    r = c.post(
        "/api/curves/run", json={"report_month": "2026-07-01", "preset": "PARITY_JUL26", "source": "fixtures"}
    )
    assert r.status_code == 422 and "not fittable" in r.json()["detail"]


def test_fixtures_source_missing_gives_503(monkeypatch):
    monkeypatch.setenv("NUTUN_FIXTURES_DIR", "C:/definitely/not/here")
    from api.deps import _settings

    _settings.cache_clear()
    r = TestClient(app).post(
        "/api/curves/run", json={"report_month": "2026-07-01", "preset": "PARITY_JUL26", "source": "fixtures"}
    )
    assert r.status_code == 503 and "fixtures" in r.json()["detail"].lower()
    _settings.cache_clear()


@pytest.mark.tieout
def test_run_from_fixtures_and_read_back(fixtures_dir):
    c = TestClient(app)
    r = c.post(
        "/api/curves/run",
        json={"report_month": "2026-07-01", "preset": "PARITY_JUL26", "source": "fixtures", "modes": ["TWO_PARAM_FIXED_MU"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rid = body["run_id"]
    assert body["n_fits"] == 48 and body["n_not_fittable"] == 0 and body["timings"]["total"] > 0
    params = c.get(f"/api/curves/{rid}/params").json()
    assert len(params) == 48 and {"k", "vb", "m", "s", "cn", "Warn", "status"} <= set(params[0])
    grids = c.get(f"/api/curves/{rid}/grids", params={"rule_set": "ROLLING", "k": 0}).json()
    assert len(grids) == 360 and grids[0]["t"] == 1
    curves = c.get(f"/api/curves/{rid}/curves").json()
    assert len(curves) == 3000 and set(curves[0]) == {"vb", "t", "curve", "lb", "ub"}
    assert c.get(f"/api/curves/{rid}/fit/TWO_PARAM_FIXED_MU/0/11").json()["status"] == "OK"
    assert c.get(f"/api/curves/{rid}/fit/THREE_PARAM/0/11").status_code == 404
    assert c.get(f"/api/curves/{rid}/bounds/11").status_code == 404  # parity bounds need the THREE_PARAM fits
    r2 = c.post(
        "/api/curves/run", json={"report_month": "2026-07-01", "preset": "PARITY_JUL26", "source": "fixtures"}
    )
    rid2 = r2.json()["run_id"]
    b = c.get(f"/api/curves/{rid2}/bounds/11")
    assert b.status_code == 200
    assert set(b.json()["sensitivity"]) == {"m-1%", "m+1%", "s-1%", "s+1%", "cn-1%", "cn+1%"}
    assert len(b.json()["table"]) == 60 and b.json()["params_from"].startswith("override ROLLING")
    csv = c.get(f"/api/curves/{rid}/paste-block.csv")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("t,11,15,22,23,25,44,UB 11")
    assert len(c.get("/api/curves/runs").json()) == 2

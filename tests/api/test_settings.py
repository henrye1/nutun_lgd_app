from api.settings import Settings


def test_windows_auth_connect_string(monkeypatch):
    monkeypatch.setenv("NUTUN_DB_SERVER", "192.168.0.55,1495")
    monkeypatch.setenv("NUTUN_DB_NAME", "Nutun_Audit_2026_July26")
    monkeypatch.setenv("NUTUN_DB_AUTH", "windows")
    s = Settings(_env_file=None)
    cs = s.odbc_connect_string()
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in cs and "SERVER=192.168.0.55,1495" in cs
    assert "DATABASE=Nutun_Audit_2026_July26" in cs and "Trusted_Connection=yes" in cs
    assert "ApplicationIntent=ReadOnly" in cs and "TrustServerCertificate=yes" in cs
    assert "PWD" not in cs and s.client_db_configured()


def test_sql_auth_uses_user_and_password_and_is_not_logged(monkeypatch):
    monkeypatch.setenv("NUTUN_DB_SERVER", "h,1")
    monkeypatch.setenv("NUTUN_DB_NAME", "d")
    monkeypatch.setenv("NUTUN_DB_AUTH", "sql")
    monkeypatch.setenv("NUTUN_DB_USER", "u")
    monkeypatch.setenv("NUTUN_DB_PASSWORD", "secret")
    s = Settings(_env_file=None)
    assert "UID=u;PWD=secret" in s.odbc_connect_string()
    assert "secret" not in repr(s) and "secret" not in str(s.public())


def test_unconfigured_when_server_missing(monkeypatch):
    monkeypatch.delenv("NUTUN_DB_SERVER", raising=False)
    assert not Settings(_env_file=None).client_db_configured()


def test_connect_string_refuses_empty_server(monkeypatch):
    import pytest

    monkeypatch.delenv("NUTUN_DB_SERVER", raising=False)
    with pytest.raises(ValueError, match="NUTUN_DB_SERVER"):
        Settings(_env_file=None).odbc_connect_string()

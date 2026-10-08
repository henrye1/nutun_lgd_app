"""Connection settings (spec §3.4). Values come from the environment or a git-ignored .env; never from code."""
from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NUTUN_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_server: str = ""
    db_name: str = ""
    db_auth: Literal["windows", "sql"] = "windows"
    db_user: str = ""
    db_password: SecretStr = SecretStr("")
    db_trust_cert: bool = True
    db_driver: str = "ODBC Driver 18 for SQL Server"
    run_store_url: str = "sqlite:///data/nutun_app.db"

    def client_db_configured(self) -> bool:
        return bool(self.db_server and self.db_name)

    def odbc_connect_string(self) -> str:
        parts = [
            f"DRIVER={{{self.db_driver}}}",
            f"SERVER={self.db_server}",
            f"DATABASE={self.db_name}",
            "ApplicationIntent=ReadOnly",
            f"TrustServerCertificate={'yes' if self.db_trust_cert else 'no'}",
            "Encrypt=yes",
        ]
        if self.db_auth == "windows":
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={self.db_user};PWD={self.db_password.get_secret_value()}")
        return ";".join(parts)

    def public(self) -> dict:
        """Settings safe to show in the UI (no password)."""
        return {"server": self.db_server, "database": self.db_name, "auth": self.db_auth, "driver": self.db_driver}

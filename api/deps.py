from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy import Engine

from api.catalog import Catalog, SqlServerCatalog
from api.db import make_client_engine
from api.settings import Settings


@lru_cache
def _settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return _settings()


def get_engine(settings: Settings = Depends(get_settings)) -> Engine:
    return make_client_engine(settings)


def get_catalog(engine: Engine = Depends(get_engine)) -> Catalog:
    return SqlServerCatalog(engine)

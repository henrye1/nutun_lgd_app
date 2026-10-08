from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_FIXTURES = ROOT / "tests" / "fixtures" / "private"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def reference_dir() -> Path:
    """Directory holding the reference .xlsm files: reference/ if present, else the repo root."""
    ref = ROOT / "reference"
    return ref if ref.exists() else ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    if not (PRIVATE_FIXTURES / "manifest.json").exists():
        pytest.skip("private workbook fixtures not extracted (run: uv run python -m scripts.extract_fixtures)")
    return PRIVATE_FIXTURES


@pytest.fixture(scope="session")
def expected(fixtures_dir) -> dict:
    """Workbook expected values (client figures) — kept out of git in the private fixture dir."""
    import json

    return json.loads((fixtures_dir / "expected_jul26.json").read_text())


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("NUTUN_DB_SERVER"):
        skip_db = pytest.mark.skip(reason="NUTUN_DB_SERVER not set; live DB tests skipped")
        for item in items:
            if "db" in item.keywords:
                item.add_marker(skip_db)

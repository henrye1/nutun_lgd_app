# Nutun AC Valuation App

Port of the July-2026 Nutun Excel valuation workbooks to a local web app.
Spec: `Nutun_AC_Valuation_App_Specification.md`.

## Setup (Windows)
1. Install [uv](https://docs.astral.sh/uv/) and the "ODBC Driver 18 for SQL Server".
2. `uv sync --extra dev` (installs Python 3.12 and all packages into `.venv`). `uv.toml` sets `link-mode = "copy"` because the folder lives on OneDrive, where hardlinks from the uv cache fail.
3. Copy `.env.example` to `.env` and fill in the connection (never commit `.env`).
4. Deploy `sql/fn_APP_Info.sql` once in SSMS (the only new SQL object).
5. Extract test fixtures from the reference workbooks:
   `uv run python -m scripts.extract_fixtures`
6. Run the tests: `uv run pytest`.

## Layout
See spec §3.3. `nutun_engine/` is the calculation engine (no I/O); `api/` is FastAPI; `web/` is the React front end.

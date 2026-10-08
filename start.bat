@echo off
cd /d "%~dp0"
if "%NUTUN_PORT%"=="" set NUTUN_PORT=8000
if not exist web\dist (echo Building the front end... && pushd web && call npm run build && popd)
start "" http://127.0.0.1:%NUTUN_PORT%/data
uv run --env-file .env uvicorn api.main:app --host 127.0.0.1 --port %NUTUN_PORT%

@echo off
cd /d "%~dp0"
rem Port: NUTUN_PORT from the shell, else from .env, else 8000. The server binds to 127.0.0.1 only.
if "%NUTUN_PORT%"=="" if exist .env for /f "usebackq tokens=1,* delims==" %%a in (`findstr /b /i "NUTUN_PORT=" .env`) do set NUTUN_PORT=%%b
if "%NUTUN_PORT%"=="" set NUTUN_PORT=8000
if not exist web\dist (echo Building the front end... && pushd web && call npm run build && popd)
start "" http://127.0.0.1:%NUTUN_PORT%/data
uv run --env-file .env uvicorn api.main:app --host 127.0.0.1 --port %NUTUN_PORT%

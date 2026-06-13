@echo off
setlocal
cd /d "%~dp0"
REM Stages source only (see scripts\push.py) — logs, data, .env, and .venv stay local.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\push.py %*
) else (
    python scripts\push.py %*
)

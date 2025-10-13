@echo off
setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

set PYTHON_BIN=python3.12
where %PYTHON_BIN% >nul 2>&1
if %errorlevel% neq 0 (
    echo python3.12 not found. Install Python 3.12 and rerun this script.
    exit /b 1
)

if not exist ".venv" (
    %PYTHON_BIN% -m venv .venv
)

set "VENV_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe"

call ".venv\Scripts\activate.bat"
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
"%VENV_PY%" app.py

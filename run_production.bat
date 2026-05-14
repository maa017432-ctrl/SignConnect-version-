@echo off
REM SignConnect - Production HTTP server (Waitress)
REM Usage: run_production.bat
REM
REM NOTE: WebSocket connections fall back to HTTP long-polling in this mode.

SET "PROJECT_ROOT=%~dp0"
SET "PYTHON_EXE=%PROJECT_ROOT%.venv311\Scripts\python.exe"
SET "WAITRESS=%PROJECT_ROOT%.venv311\Scripts\waitress-serve.exe"
SET "PORT=5000"
SET "HOST=0.0.0.0"

IF NOT EXIST "%PYTHON_EXE%" (
    echo ERROR: .venv311 not found.
    pause & exit /b 1
)

IF NOT EXIST "%WAITRESS%" (
    echo Installing waitress...
    "%PYTHON_EXE%" -m pip install waitress
)

echo.
echo   SignConnect -- Production Mode (Waitress)
echo   Server : http://%HOST%:%PORT%
echo   Threads: 8 workers
echo.

cd /d "%PROJECT_ROOT%"
"%WAITRESS%" --host=%HOST% --port=%PORT% --threads=8 --call "app:create_app"

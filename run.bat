@echo off
REM SignConnect launcher - always uses the .venv311 Python 3.11 interpreter.
REM Usage: run.bat  (double-click or call from CMD)
REM Do NOT use plain "python app.py" - that picks up the wrong global Python.

SET "PROJECT_ROOT=%~dp0"
SET "PYTHON_EXE=%PROJECT_ROOT%.venv311\Scripts\python.exe"

IF NOT EXIST "%PYTHON_EXE%" (
    echo.
    echo ERROR: .venv311 not found at %PYTHON_EXE%
    echo.
    echo Set it up once with:
    echo   py -3.11 -m venv .venv311
    echo   .venv311\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

IF NOT EXIST "%PROJECT_ROOT%models\gesture_model.h5" (
    echo Model not found - generating demo model...
    "%PYTHON_EXE%" "%PROJECT_ROOT%scripts\generate_demo_model.py"
    IF ERRORLEVEL 1 (
        echo ERROR: Demo model generation failed.
        exit /b 1
    )
)

echo Starting SignConnect using %PYTHON_EXE% ...
"%PYTHON_EXE%" "%PROJECT_ROOT%app.py"

# SignConnect launcher - always uses the .venv311 Python 3.11 interpreter.
# Usage: .\run.ps1
# Do NOT use plain "python app.py" - that picks up the wrong global Python.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv311\Scripts\python.exe"
$DemoModelScript = Join-Path $ProjectRoot "scripts\generate_demo_model.py"
$AppScript = Join-Path $ProjectRoot "app.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error ".venv311 not found at: $PythonExe`n`nSet it up once with:`n    py -3.11 -m venv .venv311`n    .\.venv311\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

$ModelPath = Join-Path $ProjectRoot "models\gesture_model.h5"
if (-not (Test-Path $ModelPath)) {
    Write-Host "Model not found - generating demo model..." -ForegroundColor Yellow
    & $PythonExe $DemoModelScript
    if ($LASTEXITCODE -ne 0) {
        throw "Demo model generation failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Starting SignConnect using $PythonExe ..." -ForegroundColor Cyan
& $PythonExe $AppScript

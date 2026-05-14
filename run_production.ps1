# SignConnect - Production HTTP server (Waitress)
#
# Usage: .\run_production.ps1
#
# Waitress is a pure-Python, multi-threaded WSGI server — no C compiler
# required and fully supported on Windows.
#
# NOTE: WebSocket connections fall back to HTTP long-polling in this mode.
# For full WebSocket support use the dev launcher (.\run.ps1) or deploy
# behind a reverse proxy (nginx) that handles the WebSocket upgrade.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv311\Scripts\python.exe"
$Waitress = Join-Path $ProjectRoot ".venv311\Scripts\waitress-serve.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Error "venv311 not found. Run: .\run.ps1 first (it will guide you)."
    exit 1
}

if (-not (Test-Path $Waitress)) {
    Write-Host "Installing waitress..." -ForegroundColor Yellow
    & $PythonExe -m pip install waitress
}

# Load PORT from .env if present
$EnvFile = Join-Path $ProjectRoot ".env"
$Port = "5000"
$Host = "0.0.0.0"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^PORT=(.+)$")  { $Port = $Matches[1].Trim() }
        if ($_ -match "^HOST=(.+)$")  { $Host = $Matches[1].Trim() }
    }
}

Write-Host ""
Write-Host "  SignConnect - Production Mode (Waitress)" -ForegroundColor Cyan
Write-Host "  Server : http://${Host}:${Port}" -ForegroundColor Cyan
Write-Host "  Threads: 8 workers" -ForegroundColor Cyan
Write-Host "  Note   : WebSocket falls back to long-polling in this mode." -ForegroundColor DarkYellow
Write-Host ""

Set-Location $ProjectRoot
& $Waitress `
    --host=$Host `
    --port=$Port `
    --threads=8 `
    --connection-limit=500 `
    --channel-timeout=120 `
    --call "app:create_app"

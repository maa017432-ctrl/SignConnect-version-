# SignConnect - One-command post-pull setup and launcher
# Usage:  .\setup_and_run.ps1
#         .\setup_and_run.ps1 -SkipDiagnostics
#         .\setup_and_run.ps1 -ForceRecreateVenv

[CmdletBinding()]
param(
    [switch]$SkipDiagnostics,
    [switch]$ForceRecreateVenv,
    [switch]$SkipModelGeneration,
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv311"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$ReqFile = Join-Path $ProjectRoot "requirements.txt"
$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
$ModelPath = Join-Path $ProjectRoot "models\gesture_model.h5"
$DemoMarker = Join-Path $ProjectRoot "models\gesture_model.demo"
$LabelMapPath = Join-Path $ProjectRoot "models\label_map.json"
$DiagScript = Join-Path $ProjectRoot "scripts\diagnose.py"
$DemoModelScript = Join-Path $ProjectRoot "scripts\generate_demo_model.py"
$AppScript = Join-Path $ProjectRoot "app.py"

function Write-Title($text) {
    Write-Host ("
=== $text ===") -ForegroundColor Cyan
}

function Write-Success($text) {
    Write-Host "  OK: $text" -ForegroundColor Green
}

function Write-Warn($text) {
    Write-Host "  WARN: $text" -ForegroundColor Yellow
}

function Write-Fail($text) {
    Write-Host "  FAIL: $text" -ForegroundColor Red
}

# -- 1. Resolve Python executable --
Write-Title "Step 1/8 - Locating Python $PythonVersion"

$GlobalPython = $null
$ver = $null
try { $ver = (& py -$PythonVersion --version) 2>$null } catch {}
if ($ver) {
    $GlobalPython = "py"
    Write-Success "Found Python: py -$PythonVersion => $ver"
} else {
    try { $ver = (& python --version) 2>$null } catch {}
    if ($ver -match "3\.(11|12)") {
        $GlobalPython = "python"
        Write-Success "Found Python: python => $ver"
    }
}

if (-not $GlobalPython) {
    Write-Fail "Python 3.11 or 3.12 is required but not found."
    Write-Host "Install from https://www.python.org/downloads/ and ensure 'py' launcher is on PATH."
    exit 1
}

# -- 2. Virtual environment --
Write-Title "Step 2/8 - Virtual environment (.venv311)"

if ($ForceRecreateVenv -and (Test-Path $VenvDir)) {
    Write-Warn "ForceRecreateVenv set - removing existing .venv311"
    Remove-Item -Recurse -Force $VenvDir
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating virtual environment with $GlobalPython ..."
    if ($GlobalPython -eq "py") {
        & py -$PythonVersion -m venv $VenvDir
    } else {
        & python -m venv $VenvDir
    }
    if (-not (Test-Path $PythonExe)) {
        Write-Fail "Failed to create .venv311"
        exit 1
    }
    Write-Success "Created .venv311"
} else {
    Write-Success ".venv311 already exists"
}

# -- 3. Upgrade pip / install requirements --
Write-Title "Step 3/8 - Installing / updating dependencies"

& $PythonExe -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Null

$pipResult = & $PythonExe -m pip install -r $ReqFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install failed. Common fixes:"
    Write-Host "  1. Ensure you have a stable internet connection."
    Write-Host "  2. Try:  $PythonExe -m pip install tensorflow==2.15.1 mediapipe==0.10.30 protobuf 'numpy>=1.26.0'"
    exit 1
}
Write-Success "Requirements installed"

# -- 4. Ensure .env file exists --
Write-Title "Step 4/8 - Environment file (.env)"

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Success "Created .env from .env.example"
        Write-Warn "Please review .env and change SECRET_KEY and API_KEY before production use."
    } else {
        Write-Fail ".env.example not found. Cannot create .env"
        exit 1
    }
} else {
    Write-Success ".env already exists"
}

# -- 5. Ensure required directories --
Write-Title "Step 5/8 - Required directories"

@("models", "database", "static\audio", "logs") | ForEach-Object {
    $d = Join-Path $ProjectRoot $_
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Success "Created $_"
    } else {
        Write-Success "$_ exists"
    }
}

# -- 6. Clean stale demo marker and ensure model --
Write-Title "Step 6/8 - Model file check"

if (Test-Path $DemoMarker) {
    Write-Warn "Removing stale demo marker: $DemoMarker"
    Remove-Item $DemoMarker -Force
}

if (-not (Test-Path $LabelMapPath)) {
    Write-Fail "label_map.json is missing. Pull it from the repo (it should NOT be gitignored)."
    exit 1
}

if (-not $SkipModelGeneration) {
    if (-not (Test-Path $ModelPath)) {
        Write-Host "Generating demo model (untrained placeholder) ..."
        & $PythonExe $DemoModelScript
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Demo model generation failed."
            exit 1
        }
        Write-Success "Demo model generated at $ModelPath"
        Write-Warn "This is an UNTRAINED model. Replace with a real trained model for accurate predictions."
    } else {
        Write-Success "Model found: $ModelPath"
    }
} else {
    Write-Success "Skipped model generation ( -SkipModelGeneration )"
}

# -- 7. Run diagnostics --
if (-not $SkipDiagnostics) {
    Write-Title "Step 7/8 - Environment diagnostics"
    & $PythonExe $DiagScript
} else {
    Write-Success "Skipped diagnostics ( -SkipDiagnostics )"
}

# -- 8. Launch --
Write-Title "Step 8/8 - Starting SignConnect"
Write-Host "Open http://localhost:5000 in your browser once the server starts." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

& $PythonExe $AppScript

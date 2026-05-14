param(
  [int[]]$Tiers = @(50, 100, 300),
  [int]$ChunkSize = 80,
  [int]$SequenceLength = 30,
  [int]$MinDetectedFrames = 6,
  [int]$CheckpointEvery = 10,
  [int]$ProgressEvery = 10,
  [switch]$ForceExtract,
  [switch]$SkipTraining
)

$ErrorActionPreference = "Stop"

function Get-MinVideosPerClass([int]$Tier) {
  if ($Tier -le 50) { return 20 }
  return 10
}

function Get-Epochs([int]$Tier) {
  if ($Tier -ge 300) { return 80 }
  return 60
}

function Invoke-Native(
  [string]$Exe,
  [string[]]$Arguments,
  [string]$LogFile
) {
  $quotedArgs = $Arguments | ForEach-Object {
    if ($_ -match '[\s"]') {
      '"' + ($_ -replace '"', '\"') + '"'
    } else {
      $_
    }
  }
  $argLine = $quotedArgs -join " "

  Write-Host ""
  Write-Host ">> $Exe $argLine"
  $stdoutPath = [System.IO.Path]::GetTempFileName()
  $stderrPath = [System.IO.Path]::GetTempFileName()
  try {
    $proc = Start-Process `
      -FilePath $Exe `
      -ArgumentList $argLine `
      -NoNewWindow `
      -Wait `
      -PassThru `
      -RedirectStandardOutput $stdoutPath `
      -RedirectStandardError $stderrPath

    if (Test-Path $stdoutPath) {
      Get-Content $stdoutPath | Tee-Object -FilePath $LogFile -Append
    }
    if (Test-Path $stderrPath) {
      Get-Content $stderrPath | Tee-Object -FilePath $LogFile -Append
    }

    if ($proc.ExitCode -ne 0) {
      throw "Command failed with exit code $($proc.ExitCode). See log: $LogFile"
    }
  } finally {
    if (Test-Path $stdoutPath) { Remove-Item $stdoutPath -Force }
    if (Test-Path $stderrPath) { Remove-Item $stderrPath -Force }
  }
}

function Get-DatasetSampleCount(
  [string]$PythonExe,
  [string]$DatasetPath
) {
  if (-not (Test-Path $DatasetPath)) { return 0 }
  $count = & $PythonExe -c "import numpy as np; d=np.load(r'$DatasetPath',allow_pickle=True); print(len(d['labels']))"
  return [int]($count.Trim())
}

function Get-ManifestState([string]$ManifestPath) {
  if (-not (Test-Path $ManifestPath)) { return $null }
  try {
    return Get-Content $ManifestPath -Raw | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv311\Scripts\python.exe"
$Extractor = Join-Path $ProjectRoot "scripts\wlasl_to_sequences.py"
$Trainer = Join-Path $ProjectRoot "scripts\train_temporal.py"
$LogsDir = Join-Path $ProjectRoot "logs\tier_pipeline"

Ensure-Dir $LogsDir

if (-not (Test-Path $PythonExe)) {
  throw "Python virtualenv not found: $PythonExe"
}
if (-not (Test-Path $Extractor)) {
  throw "Extractor script not found: $Extractor"
}
if (-not (Test-Path $Trainer)) {
  throw "Trainer script not found: $Trainer"
}

Set-Location $ProjectRoot

Write-Host "==============================================================="
Write-Host "SignConnect - Full WLASL Tier Pipeline"
Write-Host "Project: $ProjectRoot"
Write-Host "Tiers: $($Tiers -join ', ')"
Write-Host "Chunk size: $ChunkSize"
Write-Host "==============================================================="

foreach ($Tier in $Tiers) {
  $minVideos = Get-MinVideosPerClass $Tier
  $epochs = Get-Epochs $Tier

  $dataset = Join-Path $ProjectRoot "data\wlasl_sequences\tier${Tier}_sequences.npz"
  $manifest = Join-Path $ProjectRoot "data\wlasl_sequences\tier${Tier}_sequences.json"

  $extractLog = Join-Path $LogsDir "tier${Tier}_extract.log"
  $trainLog = Join-Path $LogsDir "tier${Tier}_train.log"

  if ($ForceExtract) {
    if (Test-Path $dataset) { Remove-Item $dataset -Force }
    if (Test-Path $manifest) { Remove-Item $manifest -Force }
  }

  Write-Host ""
  Write-Host "-------------------- Tier ${Tier}: Extraction --------------------"
  $previousCount = Get-DatasetSampleCount $PythonExe $dataset
  $stalledRuns = 0
  $runIndex = 0

  while ($true) {
    $runIndex++
    Write-Host "Tier $Tier extraction chunk #$runIndex"

    $extractArgs = @(
      "-u", $Extractor,
      "--max-classes", "$Tier",
      "--min-videos-per-class", "$minVideos",
      "--sequence-length", "$SequenceLength",
      "--min-detected-frames", "$MinDetectedFrames",
      "--checkpoint-every", "$CheckpointEvery",
      "--progress-every", "$ProgressEvery",
      "--max-clips-this-run", "$ChunkSize",
      "--output", $dataset
    )
    Invoke-Native $PythonExe $extractArgs $extractLog

    $currentCount = Get-DatasetSampleCount $PythonExe $dataset
    Write-Host "Tier $Tier samples: $previousCount -> $currentCount"
    $manifestState = Get-ManifestState $manifest
    if ($manifestState -and $manifestState.is_complete -eq $true) {
      Write-Host "Tier $Tier extraction complete (manifest is_complete=true)."
      break
    }

    if ($currentCount -gt $previousCount) {
      $previousCount = $currentCount
      $stalledRuns = 0
      continue
    }

    $stalledRuns++
    if ($stalledRuns -lt 2) {
      continue
    }

    Write-Host "No growth for 2 chunks; running final completion pass..."
    $finalArgs = @(
      "-u", $Extractor,
      "--max-classes", "$Tier",
      "--min-videos-per-class", "$minVideos",
      "--sequence-length", "$SequenceLength",
      "--min-detected-frames", "$MinDetectedFrames",
      "--checkpoint-every", "$CheckpointEvery",
      "--progress-every", "$ProgressEvery",
      "--output", $dataset
    )
    Invoke-Native $PythonExe $finalArgs $extractLog

    $finalCount = Get-DatasetSampleCount $PythonExe $dataset
    Write-Host "Tier $Tier post-final-pass samples: $finalCount"
    $finalManifestState = Get-ManifestState $manifest
    if ($finalManifestState -and $finalManifestState.is_complete -eq $true) {
      Write-Host "Tier $Tier extraction complete (post-final manifest check)."
      break
    }
    if ($finalCount -le $currentCount) {
      Write-Host "Tier $Tier extraction complete."
      break
    }

    $previousCount = $finalCount
    $stalledRuns = 0
  }

  if ($SkipTraining) {
    Write-Host "Tier $Tier training skipped."
    continue
  }

  Write-Host ""
  Write-Host "-------------------- Tier ${Tier}: Training ----------------------"
  $trainArgs = @(
    $Trainer,
    "--data", $dataset,
    "--max-classes", "$Tier",
    "--min-samples-per-class", "8",
    "--epochs", "$epochs",
    "--batch-size", "16"
  )
  Invoke-Native $PythonExe $trainArgs $trainLog

  Write-Host "Saving tier-specific snapshots..."
  $modelsDir = Join-Path $ProjectRoot "models"
  $snapMetrics = Join-Path $modelsDir "temporal_metrics_tier$Tier.json"
  $snapConf = Join-Path $modelsDir "temporal_confusion_tier$Tier.csv"
  $snapModel = Join-Path $modelsDir "gesture_model_tier$Tier.h5"
  $snapLabel = Join-Path $modelsDir "label_map_tier$Tier.json"
  $snapNorm = Join-Path $modelsDir "norm_stats_tier$Tier.npz"

  Copy-Item (Join-Path $modelsDir "temporal_metrics.json") $snapMetrics -Force
  Copy-Item (Join-Path $modelsDir "temporal_confusion_matrix.csv") $snapConf -Force
  Copy-Item (Join-Path $modelsDir "gesture_model.h5") $snapModel -Force
  Copy-Item (Join-Path $modelsDir "label_map.json") $snapLabel -Force
  Copy-Item (Join-Path $modelsDir "norm_stats.npz") $snapNorm -Force
}

Write-Host ""
Write-Host "==============================================================="
Write-Host "Pipeline finished."
Write-Host "Logs: $LogsDir"
Write-Host "==============================================================="

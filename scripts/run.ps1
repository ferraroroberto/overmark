#Requires -Version 5.1
<#
.SYNOPSIS
    Start Overmark from this checkout. Without -Console this is tray.bat (the standard start);
    -Console runs the same module in this console so the log shows while debugging.

.DESCRIPTION
    Settings are read from config.json in the repo root, created from
    config.sample.json on first run.
#>
param([switch]$Console)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Console) {
    & (Join-Path $root 'tray.bat')
    exit $LASTEXITCODE
}
$env:PYTHONPATH = Join-Path $root 'src'
$py = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { Write-Error "No .venv: run 'py -m venv .venv' then pip install -r requirements.txt"; exit 1 }
& $py -m overmark @args

#Requires -Version 5.1
<#
.SYNOPSIS
    Start Overmark from this checkout with the repo's .venv (no console window).

.DESCRIPTION
    Settings are read from config.json in the repo root, created from
    config.sample.json on first run. Pass -Console to keep a console with the log.
#>
param([switch]$Console)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root 'src'
$exe = if ($Console) { 'python.exe' } else { 'pythonw.exe' }
$py = Join-Path $root ".venv/Scripts/$exe"
if (-not (Test-Path $py)) { Write-Error "No .venv: run 'py -m venv .venv' then pip install -r requirements.txt"; exit 1 }
if ($Console) { & $py -m overmark @args } else { Start-Process -FilePath $py -ArgumentList '-m', 'overmark' -WorkingDirectory $root }

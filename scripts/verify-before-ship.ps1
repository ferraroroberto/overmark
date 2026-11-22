#Requires -Version 5.1
<#
.SYNOPSIS
    Pre-ship verification gate. One pass/fail pipeline, fail-fast.

.DESCRIPTION
    Stages: byte-compile (src, tests), ruff lint, then run_ratchets.py (every enabled
    ratchet, then pytest and the runtime write probe). Run from the repo root with
    the repo's own .venv; nothing is activated.
#>
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$py = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $py)) { Write-Error "No .venv: run 'py -m venv .venv' then pip install -r requirements-dev.txt"; exit 1 }

function Invoke-Stage([string]$Name, [scriptblock]$Body) {
    Write-Host "== $Name"
    & $Body
    if ($LASTEXITCODE -ne 0) { Write-Host "GATE-RESULT: FAIL ($Name)"; exit 1 }
}

Invoke-Stage 'byte-compile' { & $py -m compileall -q src tests }
Invoke-Stage 'ruff' { & $py -m ruff check . }
# Exit 3 from a ratchet means not confirmed; the runner reports it and fails, never passes.
Invoke-Stage 'ratchets and pytest' { & $py scripts/run_ratchets.py --tests $py -m pytest -q }
Write-Host 'GATE-RESULT: PASS'

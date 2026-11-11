$ErrorActionPreference = 'Stop'
$ExperimentRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $ExperimentRoot 'backend')
& (Join-Path $ExperimentRoot '.venv/Scripts/python.exe') -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

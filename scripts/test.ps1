$ErrorActionPreference = 'Stop'
$ExperimentRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $ExperimentRoot 'backend')
& (Join-Path $ExperimentRoot '.venv/Scripts/python.exe') -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
Set-Location -LiteralPath (Join-Path $ExperimentRoot 'frontend')
npm run test
if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }

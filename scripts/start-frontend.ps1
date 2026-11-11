$ErrorActionPreference = 'Stop'
$ExperimentRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath (Join-Path $ExperimentRoot 'frontend')
npm run dev

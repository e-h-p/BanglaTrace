$ErrorActionPreference = 'Stop'
$ExperimentRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ExperimentRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.11 or newer and add it to PATH, then run setup again.'
    }
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
& './.venv/Scripts/python.exe' -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The project virtual environment requires a working Python 3.11 or newer installation.' }
& './.venv/Scripts/python.exe' -m pip install --cache-dir '.runtime/pip-cache' -r 'backend/requirements.txt'
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
Set-Location -LiteralPath (Join-Path $ExperimentRoot 'frontend')
& npm.cmd ci --cache '../.runtime/npm-cache'
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
Write-Host 'Setup complete. Run start.cmd, or use scripts/start-backend.ps1 and scripts/start-frontend.ps1 in separate terminals for development.'

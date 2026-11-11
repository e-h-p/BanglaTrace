$ErrorActionPreference = 'Stop'
$ExperimentRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ExperimentRoot '.venv/Scripts/python.exe'

if (-not (Get-Command node -ErrorAction SilentlyContinue) -or
    -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Install Node.js 22.12 or newer, then run start.cmd again.'
}
$NodeVersion = & node --version
if ($LASTEXITCODE -ne 0 -or [version]($NodeVersion.TrimStart('v')) -lt [version]'22.12.0') {
    throw 'Node.js 22.12 or newer is required.'
}

# Check before installing/building so an occupied port fails immediately.
$Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
try {
    $Listener.Start()
} catch {
    throw 'Port 8000 is already in use. If BanglaPlag is running, open http://127.0.0.1:8000; otherwise stop the process using this port and retry.'
} finally {
    $Listener.Stop()
}

$NeedsSetup = -not (Test-Path -LiteralPath $Python)
if (-not $NeedsSetup) {
    & $Python -c "import importlib.util, sys; sys.exit(any(importlib.util.find_spec(name) is None for name in ('fastapi', 'uvicorn', 'dotenv', 'fitz', 'numpy', 'rapidfuzz', 'rank_bm25', 'sentence_transformers', 'httpx', 'multipart')))"
    $NeedsSetup = $LASTEXITCODE -ne 0
}
if ($NeedsSetup -or -not (Test-Path -LiteralPath (Join-Path $ExperimentRoot 'frontend/node_modules/.bin/vite.cmd'))) {
    Write-Host 'Installing project dependencies...'
    & (Join-Path $PSScriptRoot 'setup.ps1')
}

Push-Location -LiteralPath (Join-Path $ExperimentRoot 'frontend')
try {
    Write-Host 'Building the frontend...'
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally {
    Pop-Location
}

Push-Location -LiteralPath (Join-Path $ExperimentRoot 'backend')
try {
    Write-Host ''
    Write-Host 'Open http://127.0.0.1:8000 when the server reports Application startup complete.'
    Write-Host 'Keep this window open. Press Ctrl+C to stop BanglaPlag.'
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Backend startup failed. See the server error above.' }
} finally {
    Pop-Location
}

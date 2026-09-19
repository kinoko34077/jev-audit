$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Run .\setup.ps1 first."
    exit 1
}

& $python -m jev_audit.mcp_server
exit $LASTEXITCODE

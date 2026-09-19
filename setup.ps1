$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".venv")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[mcp]"

Write-Host ""
Write-Host "Setup complete."
Write-Host "CLI : .\audit.ps1 ."
Write-Host "MCP : .\mcp.ps1"

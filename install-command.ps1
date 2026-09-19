$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Run .\setup.ps1 first."
    exit 1
}

$bin = Join-Path $env:LOCALAPPDATA "jev-audit\bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null

$cli = Join-Path $bin "jev-audit.cmd"
$mcp = Join-Path $bin "jev-audit-mcp.cmd"

@"
@echo off
"$python" -m jev_audit.cli %*
"@ | Set-Content -Encoding ASCII $cli

@"
@echo off
"$python" -m jev_audit.mcp_server %*
"@ | Set-Content -Encoding ASCII $mcp

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = @()
if ($userPath) {
    $entries = $userPath.Split(';') | Where-Object { $_ -ne '' }
}

if ($entries -notcontains $bin) {
    $newPath = (($entries + $bin) -join ';')
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added to User PATH: $bin"
    Write-Host "Open a new terminal before using jev-audit globally."
} else {
    Write-Host "Already in User PATH: $bin"
}

Write-Host "CLI launcher: $cli"
Write-Host "MCP launcher: $mcp"

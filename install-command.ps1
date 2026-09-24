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
$cliPs1 = Join-Path $bin "jev-audit.ps1"
$mcpPs1 = Join-Path $bin "jev-audit-mcp.ps1"

# Keep the generated .cmd files ASCII-only so cmd.exe never has to decode the
# repository path.  The Unicode Python path lives in a UTF-8-with-BOM PowerShell
# shim, which PowerShell 5.1 and newer can read reliably.
$ascii = [System.Text.ASCIIEncoding]::new()
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
$quotedPython = $python.Replace("'", "''")
$cliPs1Content = "& '{0}' -m jev_audit.cli @args`r`nexit `$LASTEXITCODE`r`n" -f $quotedPython
$mcpPs1Content = "& '{0}' -m jev_audit.mcp_server @args`r`nexit `$LASTEXITCODE`r`n" -f $quotedPython
$cliContent = '@echo off' + "`r`n" + 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0jev-audit.ps1" %*' + "`r`n"
$mcpContent = '@echo off' + "`r`n" + 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0jev-audit-mcp.ps1" %*' + "`r`n"
[System.IO.File]::WriteAllText($cliPs1, $cliPs1Content, $utf8Bom)
[System.IO.File]::WriteAllText($mcpPs1, $mcpPs1Content, $utf8Bom)
[System.IO.File]::WriteAllText($cli, $cliContent, $ascii)
[System.IO.File]::WriteAllText($mcp, $mcpContent, $ascii)

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

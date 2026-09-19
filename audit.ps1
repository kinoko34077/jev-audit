$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Run .\setup.ps1 first."
    exit 1
}

if ($args.Count -eq 0) {
    & $python -m jev_audit.cli "."
} else {
    & $python -m jev_audit.cli @args
}
exit $LASTEXITCODE

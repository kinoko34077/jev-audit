$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

function Test-PythonCandidate {
    param(
        [Parameter(Mandatory=$true)][string]$Command,
        [string[]]$PrefixArgs = @()
    )

    try {
        $output = & $Command @PrefixArgs -c "import sys, venv; assert sys.version_info >= (3, 10), sys.version; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        $lines = @($output)
        if ($lines.Count -lt 1) {
            return $null
        }
        return [string]$lines[-1]
    }
    catch {
        return $null
    }
}

function Find-UsablePython {
    $candidates = @()

    if ($env:PYTHON) {
        $candidates += [pscustomobject]@{ Label = "PYTHON env"; Command = $env:PYTHON; Args = @() }
    }

    # Prefer direct Python commands. This avoids a stale Windows `py` launcher
    # pointing at an uninstalled Anaconda/CPython installation.
    $candidates += [pscustomobject]@{ Label = "python"; Command = "python"; Args = @() }
    $candidates += [pscustomobject]@{ Label = "python3"; Command = "python3"; Args = @() }

    # Fall back to explicit Python Launcher versions before its default target.
    foreach ($version in @("3.13", "3.12", "3.11", "3.10")) {
        $candidates += [pscustomobject]@{ Label = "py -$version"; Command = "py"; Args = @("-$version") }
    }
    $candidates += [pscustomobject]@{ Label = "py -3"; Command = "py"; Args = @("-3") }
    $candidates += [pscustomobject]@{ Label = "py"; Command = "py"; Args = @() }

    foreach ($candidate in $candidates) {
        $exe = Test-PythonCandidate -Command $candidate.Command -PrefixArgs $candidate.Args
        if ($exe) {
            return [pscustomobject]@{
                Label = $candidate.Label
                Command = $candidate.Command
                Args = $candidate.Args
                Executable = $exe
            }
        }
    }

    return $null
}

function Test-VenvPython {
    if (-not (Test-Path $venvPython)) {
        return $false
    }
    try {
        & $venvPython -c "import sys; assert sys.version_info >= (3, 10)" 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

$pythonCandidate = Find-UsablePython
if (-not $pythonCandidate) {
    Write-Host "No usable Python 3.10+ installation was found." -ForegroundColor Red
    Write-Host ""
    Write-Host "The Windows Python launcher may be pointing to an old installation."
    Write-Host "Check these commands:"
    Write-Host "  where.exe python"
    Write-Host "  where.exe py"
    Write-Host "  py -0p"
    Write-Host ""
    Write-Host "Install/re-register Python 3.10+ or set the PYTHON environment variable"
    Write-Host "to a valid python.exe, then run setup.ps1 again."
    exit 1
}

Write-Host "Using Python: $($pythonCandidate.Executable) [$($pythonCandidate.Label)]"

if (-not (Test-VenvPython)) {
    if (Test-Path $venvDir) {
        Write-Host "Removing incomplete or unusable .venv ..."
        Remove-Item -Recurse -Force $venvDir
    }

    Write-Host "Creating .venv ..."
    & $pythonCandidate.Command @($pythonCandidate.Args) -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create .venv using $($pythonCandidate.Label)."
        exit $LASTEXITCODE
    }
}

if (-not (Test-VenvPython)) {
    Write-Error ".venv was created but its Python executable is not usable."
    exit 1
}

Write-Host "Installing jev-audit and MCP dependencies ..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $venvPython -m pip install -e ".[mcp]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Setup complete."
Write-Host "Python: $venvPython"
Write-Host "CLI   : .\audit.ps1 ."
Write-Host "MCP   : .\mcp.ps1"

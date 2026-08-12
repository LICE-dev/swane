[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Action
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
Set-Location -LiteralPath $projectRoot

function Test-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Prefix = @()
    )

    try {
        & $FilePath @Prefix -c "import sys; print(sys.executable)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Get-BasePython {
    if (-not [string]::IsNullOrWhiteSpace($env:SWANE_PYTHON)) {
        if (Test-Python -FilePath $env:SWANE_PYTHON) {
            return [pscustomobject]@{ FilePath = $env:SWANE_PYTHON; Prefix = @() }
        }
        throw "SWANE_PYTHON does not point to a working Python interpreter."
    }

    $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        foreach ($selector in @("-3.11", "-3.10", "-3")) {
            if (Test-Python -FilePath $pyLauncher.Source -Prefix @($selector)) {
                return [pscustomobject]@{ FilePath = $pyLauncher.Source; Prefix = @($selector) }
            }
        }
    }

    foreach ($commandName in @("python3", "python")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($null -ne $command -and (Test-Python -FilePath $command.Source)) {
            return [pscustomobject]@{ FilePath = $command.Source; Prefix = @() }
        }
    }

    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if ((Test-Path -LiteralPath $bundledPython -PathType Leaf) -and (Test-Python -FilePath $bundledPython)) {
        return [pscustomobject]@{ FilePath = $bundledPython; Prefix = @() }
    }

    throw "A supported Python 3 interpreter was not found. Set SWANE_PYTHON or install Python."
}

$environmentCandidates = @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $projectRoot "venv\Scripts\python.exe")
)
$projectPython = $null
foreach ($candidate in $environmentCandidates) {
    if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-Python -FilePath $candidate)) {
        $projectPython = $candidate
        break
    }
}

if ($null -eq $projectPython) {
    $basePython = Get-BasePython
    Write-Host "Creating .venv with $($basePython.FilePath) $($basePython.Prefix -join ' ')"
    & $basePython.FilePath @($basePython.Prefix) -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed with exit code $LASTEXITCODE."
    }
    $projectPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
}

& $projectPython ".codex\scripts\project_actions.py" $Action
if ($LASTEXITCODE -ne 0) {
    throw "Project action '$Action' failed with exit code $LASTEXITCODE."
}

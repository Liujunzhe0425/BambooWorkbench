$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Python = if ($env:BAMBOO_PYTHON -and (Test-Path -LiteralPath $env:BAMBOO_PYTHON -PathType Leaf)) {
    $env:BAMBOO_PYTHON
} elseif (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
    $VenvPython
} else {
    'python'
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Program,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Program $($Arguments -join ' ')"
    }
}

$RuffTargets = @('app', 'core', 'ui', 'mock_modules', 'scripts', 'tests')
$ModuleTestTargets = @()
if (Test-Path -LiteralPath (Join-Path $Root 'modules') -PathType Container) {
    $RuffTargets += 'modules'
    $ModuleTestTargets = @(
        Get-ChildItem -LiteralPath (Join-Path $Root 'modules') -Directory |
            ForEach-Object { Join-Path $_.FullName 'tests' } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    )
}

Invoke-Checked $Python -m ruff check @RuffTargets
Invoke-Checked $Python -m pytest -q
if ($ModuleTestTargets.Count -gt 0) {
    # Module suites manipulate independent import paths and some load Qt. Keep
    # them in separate processes so one module cannot leak Qt/plugin state into another.
    foreach ($ModuleTestTarget in $ModuleTestTargets) {
        Invoke-Checked $Python -m pytest -q $ModuleTestTarget
    }
}
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/moisture
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/boiling
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/after_sales
if (Test-Path -LiteralPath (Join-Path $Root 'modules') -PathType Container) {
    Get-ChildItem -LiteralPath (Join-Path $Root 'modules') -Directory | ForEach-Object {
        if (Test-Path -LiteralPath (Join-Path $_.FullName 'module.json') -PathType Leaf) {
            Invoke-Checked $Python -m app.tools.module_contract_cli validate $_.FullName
        }
    }
}
Invoke-Checked git diff --check

Write-Host 'Repository verification passed.' -ForegroundColor Green

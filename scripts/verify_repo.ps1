$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Repository .venv Python is required.'
}
$ExpectedPython = [System.IO.Path]::GetFullPath($Python)
$ActualPython = (& $Python -c 'import sys; print(sys.executable)') | Select-Object -Last 1
if ([System.IO.Path]::GetFullPath($ActualPython) -ne $ExpectedPython) {
    throw "Python interpreter is outside repository .venv: $ActualPython"
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

Invoke-Checked $Python -m ruff check app core ui mock_modules scripts tests `
    modules/moisture/src
Invoke-Checked $Python -m pytest -q
Invoke-Checked $Python -m pytest modules/moisture/tests -q
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/moisture
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/boiling
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/after_sales
Invoke-Checked $Python -m app.tools.module_contract_cli validate modules/moisture
Invoke-Checked git diff --check

Write-Host 'Repository verification passed.' -ForegroundColor Green

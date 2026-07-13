$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root

$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Python = if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
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

Invoke-Checked $Python -m ruff check app core ui mock_modules tests
Invoke-Checked $Python -m pytest -q
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/moisture
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/boiling
Invoke-Checked $Python -m app.tools.module_contract_cli validate mock_modules/after_sales
Invoke-Checked git diff --check

Write-Host 'Repository verification passed.' -ForegroundColor Green

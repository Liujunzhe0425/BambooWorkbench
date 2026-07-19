$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$ModulesRoot = Join-Path $Root 'modules'

if (-not (Test-Path -LiteralPath $ModulesRoot -PathType Container)) {
    Write-Host 'No real modules are present; skipping module runtime builds.'
    exit 0
}

$Modules = Get-ChildItem -LiteralPath $ModulesRoot -Directory | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.FullName 'module.json') -PathType Leaf
}

foreach ($Module in $Modules) {
    $Hook = Join-Path $Module.FullName 'build_portable_runtime.ps1'
    if (-not (Test-Path -LiteralPath $Hook -PathType Leaf)) {
        throw "Real module '$($Module.Name)' has no build_portable_runtime.ps1 hook."
    }

    Write-Host "Building portable runtime for $($Module.Name)..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Hook
    if ($LASTEXITCODE -ne 0) {
        throw "Portable runtime build failed for '$($Module.Name)' with exit code $LASTEXITCODE"
    }
}

Write-Host 'All real-module portable runtimes were built.' -ForegroundColor Green

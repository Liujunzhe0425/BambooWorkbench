$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Bundle = [System.IO.Path]::GetFullPath((Join-Path $Root 'dist\BambooWorkbench'))
if (-not $Bundle.StartsWith($Root.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Portable bundle escaped repository'
}

$Required = @(
    'BambooWorkbench.exe',
    'BambooModuleHost.exe',
    'contracts\schemas\module-manifest.schema.json',
    'assets\brand\team-logo.svg',
    'logo\team-logo.png',
    'logo\BambooWorkbench.ico',
    'resources\themes\bamboo.qss',
    'mock_modules\moisture\module.json',
    'mock_modules\boiling\module.json',
    'mock_modules\after_sales\module.json'
)
foreach ($Item in $Required) {
    if (-not (Test-Path -LiteralPath (Join-Path $Bundle $Item) -PathType Leaf)) {
        throw "Missing packaged file: $Item"
    }
}

$Executable = Join-Path $Bundle 'BambooWorkbench.exe'
$Process = Start-Process -FilePath $Executable -ArgumentList '--smoke-test' `
    -PassThru -WindowStyle Hidden
try {
    Wait-Process -Id $Process.Id -Timeout 90 -ErrorAction Stop
} catch {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    throw 'Packaged smoke test timed out'
}
$Process.Refresh()
if ($Process.ExitCode -ne 0) {
    throw "Packaged smoke test failed: $($Process.ExitCode)"
}
Write-Host 'Portable bundle verification passed.' -ForegroundColor Green

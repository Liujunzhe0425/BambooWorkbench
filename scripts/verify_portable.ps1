$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Bundle = [System.IO.Path]::GetFullPath((Join-Path $Root 'dist\BambooWorkbench'))
if (-not $Bundle.StartsWith($Root.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Portable bundle escaped repository'
}

$Required = @(
    'BambooWorkbench.exe',
    'BambooModuleHost.exe',
    'BambooMoistureModule.exe',
    'contracts\schemas\module-manifest.schema.json',
    'assets\brand\team-logo.svg',
    'logo\team-logo.png',
    'logo\BambooWorkbench.ico',
    'resources\themes\bamboo.qss',
    'mock_modules\moisture\module.json',
    'mock_modules\boiling\module.json',
    'mock_modules\after_sales\module.json',
    'modules\moisture\module.json',
    'modules\moisture\run_module.bat'
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
$RealProcess = Start-Process -FilePath $Executable -ArgumentList '--real-smoke-test' `
    -PassThru -WindowStyle Hidden
try {
    Wait-Process -Id $RealProcess.Id -Timeout 90 -ErrorAction Stop
} catch {
    Stop-Process -Id $RealProcess.Id -Force -ErrorAction SilentlyContinue
    throw 'Packaged real-module smoke test timed out'
}
$RealProcess.Refresh()
if ($RealProcess.ExitCode -ne 0) {
    throw "Packaged real-module smoke test failed: $($RealProcess.ExitCode)"
}
Write-Host 'Portable bundle verification passed.' -ForegroundColor Green

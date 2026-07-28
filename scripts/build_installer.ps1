$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root

& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build_portable.ps1')
if ($LASTEXITCODE -ne 0) { throw "Portable build failed with exit code $LASTEXITCODE" }

$Candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
)
$Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($Command) { $Candidates += $Command.Source }
$Compiler = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } `
    | Select-Object -First 1
if (-not $Compiler) {
    throw 'Inno Setup 6 is required. Install it, then rerun this script.'
}

& $Compiler (Join-Path $Root 'packaging\BambooWorkbench.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }

$Installer = Join-Path $Root 'installer-output\BambooWorkbench-Setup-1.3.5.exe'
if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    throw 'Installer output is missing'
}
Write-Host "Installer built: $Installer" -ForegroundColor Green

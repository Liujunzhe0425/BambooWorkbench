$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root

function Assert-RepositoryChild {
    param([Parameter(Mandatory = $true)][string]$Path)
    $Resolved = [System.IO.Path]::GetFullPath($Path)
    $Prefix = $Root.TrimEnd('\') + '\'
    if (-not $Resolved.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Build path escaped repository: $Resolved"
    }
    return $Resolved
}

$Build = Assert-RepositoryChild (Join-Path $Root 'build')
$Dist = Assert-RepositoryChild (Join-Path $Root 'dist')
foreach ($Target in @($Build, $Dist)) {
    if (Test-Path -LiteralPath $Target) {
        Remove-Item -LiteralPath $Target -Recurse -Force
    }
}

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Repository .venv Python is required for packaging.'
}
& $Python -c 'import PyInstaller'
if ($LASTEXITCODE -ne 0) {
    throw 'Packaging dependencies are missing from the repository .venv.'
}
& $Python -m PyInstaller --clean --noconfirm `
    --workpath $Build --distpath $Dist packaging\BambooWorkbench.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify_portable.ps1')
if ($LASTEXITCODE -ne 0) { throw "Portable verification failed with exit code $LASTEXITCODE" }

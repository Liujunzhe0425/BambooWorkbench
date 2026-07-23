$ErrorActionPreference = 'Stop'

$ModuleRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $ModuleRoot '..\..'))
$RepositoryPrefix = $RepositoryRoot.TrimEnd('\') + '\'

function Assert-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $Resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not $Resolved.StartsWith(
        $RepositoryPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "$Description escaped the repository: $Resolved"
    }

    $Cursor = $Resolved
    while ($Cursor.StartsWith(
        $RepositoryPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        if (Test-Path -LiteralPath $Cursor) {
            $Item = Get-Item -LiteralPath $Cursor -Force
            if ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "$Description contains a reparse point: $Cursor"
            }
        }
        $Parent = Split-Path -Parent $Cursor
        if (-not $Parent -or $Parent -eq $Cursor) {
            break
        }
        $Cursor = $Parent
    }

    return $Resolved
}

function Remove-SafeTree {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    $SafePath = Assert-RepositoryPath $Path $Description
    if (Test-Path -LiteralPath $SafePath) {
        $Item = Get-Item -LiteralPath $SafePath -Force
        if (-not $Item.PSIsContainer) {
            throw "$Description is not a directory: $SafePath"
        }
        Remove-Item -LiteralPath $SafePath -Recurse -Force
    }
}

$Python = Assert-RepositoryPath `
    (Join-Path $RepositoryRoot '.venv\Scripts\python.exe') `
    'Repository Python'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Repository virtual environment is unavailable: $Python"
}

& $Python -c 'import PyInstaller, sys; sys.version_info >= (3, 11) or sys.exit(1)'
if ($LASTEXITCODE -ne 0) {
    throw 'Repository virtual environment requires Python 3.11+ and PyInstaller.'
}

$PortableModuleRoot = Assert-RepositoryPath `
    (Join-Path $RepositoryRoot 'dist\BambooWorkbench\modules\moisture') `
    'Portable module root'
if (-not (Test-Path -LiteralPath $PortableModuleRoot -PathType Container)) {
    throw "Portable module root has not been generated: $PortableModuleRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $PortableModuleRoot 'module.json') -PathType Leaf)) {
    throw 'Portable module manifest is missing before runtime installation.'
}

$BuildRoot = Assert-RepositoryPath `
    (Join-Path $RepositoryRoot 'build\moisture-portable-runtime') `
    'Moisture runtime build root'
$WorkPath = Join-Path $BuildRoot 'work'
$SpecPath = Join-Path $BuildRoot 'spec'
$StagingDist = Join-Path $BuildRoot 'dist'
$BuiltRuntime = Join-Path $StagingDist 'BambooMoistureModule'
$TargetRuntime = Assert-RepositoryPath `
    (Join-Path $PortableModuleRoot 'runtime') `
    'Portable moisture runtime'
$IncomingRuntime = Assert-RepositoryPath `
    (Join-Path $PortableModuleRoot '.runtime.incoming') `
    'Incoming moisture runtime'
$BackupRuntime = Assert-RepositoryPath `
    (Join-Path $PortableModuleRoot '.runtime.previous') `
    'Previous moisture runtime'

$DataItems = @(
    @{ Source = 'schemas'; Destination = 'modules/moisture/schemas' },
    @{ Source = 'rules'; Destination = 'modules/moisture/rules' },
    @{ Source = 'experience'; Destination = 'modules/moisture/experience' },
    @{ Source = 'templates'; Destination = 'modules/moisture/templates' },
    @{ Source = 'samples'; Destination = 'modules/moisture/samples' },
    @{ Source = 'module.json'; Destination = 'modules/moisture' },
    @{ Source = 'run_module.bat'; Destination = 'modules/moisture' },
    @{ Source = 'run_management.bat'; Destination = 'modules/moisture' },
    @{ Source = 'README.md'; Destination = 'modules/moisture' },
    @{ Source = 'CHANGELOG.md'; Destination = 'modules/moisture' },
    @{ Source = 'requirements.txt'; Destination = 'modules/moisture' },
    @{ Source = 'pyproject.toml'; Destination = 'modules/moisture' }
)

foreach ($DataItem in $DataItems) {
    $Source = Join-Path $ModuleRoot $DataItem.Source
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Required frozen resource is missing: $($DataItem.Source)"
    }
}

Remove-SafeTree $BuildRoot 'Moisture runtime build root'
Remove-SafeTree $IncomingRuntime 'Incoming moisture runtime'
Remove-SafeTree $BackupRuntime 'Previous moisture runtime'
New-Item -ItemType Directory -Path $WorkPath, $SpecPath, $StagingDist -Force | Out-Null

$Arguments = @(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--onedir',
    '--console',
    '--noupx',
    '--name', 'BambooMoistureModule',
    '--contents-directory', '_internal',
    '--paths', (Join-Path $ModuleRoot 'src'),
    '--workpath', $WorkPath,
    '--specpath', $SpecPath,
    '--distpath', $StagingDist,
    '--log-level', 'WARN'
)
foreach ($DataItem in $DataItems) {
    $Source = Join-Path $ModuleRoot $DataItem.Source
    $Arguments += @('--add-data', "$Source;$($DataItem.Destination)")
}
$Arguments += Join-Path $ModuleRoot 'src\moisture\cli.py'

try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $BuiltExecutable = Join-Path $BuiltRuntime 'BambooMoistureModule.exe'
    if (-not (Test-Path -LiteralPath $BuiltExecutable -PathType Leaf)) {
        throw 'PyInstaller did not produce BambooMoistureModule.exe.'
    }

    Move-Item -LiteralPath $BuiltRuntime -Destination $IncomingRuntime
    try {
        if (Test-Path -LiteralPath $TargetRuntime) {
            Move-Item -LiteralPath $TargetRuntime -Destination $BackupRuntime
        }
        Move-Item -LiteralPath $IncomingRuntime -Destination $TargetRuntime
        Remove-SafeTree $BackupRuntime 'Previous moisture runtime'
    } catch {
        if (Test-Path -LiteralPath $TargetRuntime) {
            Remove-SafeTree $TargetRuntime 'Incomplete moisture runtime'
        }
        if (Test-Path -LiteralPath $BackupRuntime) {
            Move-Item -LiteralPath $BackupRuntime -Destination $TargetRuntime
        }
        throw
    }
} finally {
    Remove-SafeTree $IncomingRuntime 'Incoming moisture runtime'
    Remove-SafeTree $BuildRoot 'Moisture runtime build root'
}

Write-Host "Moisture portable runtime installed: $TargetRuntime" -ForegroundColor Green

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Installer = Join-Path $Root 'installer-output\BambooWorkbench-Setup-1.2.0.exe'
if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    throw 'Installer does not exist. Run build_installer.ps1 first.'
}

$TestRoot = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetTempPath()) `
    ("BambooWorkbench-installer-test-" + [guid]::NewGuid().ToString('N'))))
$TempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
if (-not $TestRoot.StartsWith($TempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer test root escaped the system temporary directory'
}
$InstallDir = Join-Path $TestRoot 'install'
$FakeLocalAppData = Join-Path $TestRoot 'localappdata'
New-Item -ItemType Directory -Path $InstallDir, $FakeLocalAppData -Force | Out-Null
$PriorLocalAppData = $env:LOCALAPPDATA

function Invoke-HiddenAndWait {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [int]$TimeoutSeconds = 120
    )
    $Process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -PassThru -WindowStyle Hidden
    try {
        Wait-Process -Id $Process.Id -Timeout $TimeoutSeconds -ErrorAction Stop
    } catch {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "Process timed out: $FilePath"
    }
    $Process.Refresh()
    if ($Process.ExitCode -ne 0) {
        throw "Process failed with exit code $($Process.ExitCode): $FilePath"
    }
}

try {
    $env:LOCALAPPDATA = $FakeLocalAppData
    Invoke-HiddenAndWait $Installer @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=$InstallDir"
    ) 180
    $Executable = Join-Path $InstallDir 'BambooWorkbench.exe'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw 'Silent installation did not create the application executable'
    }
    Invoke-HiddenAndWait $Executable @('--smoke-test') 90
    Invoke-HiddenAndWait $Executable @('--demo-smoke-test') 90

    $DataDirectory = Join-Path $FakeLocalAppData 'BambooWorkbench'
    New-Item -ItemType Directory -Path $DataDirectory -Force | Out-Null
    $Sentinel = Join-Path $DataDirectory 'preserve-on-uninstall.txt'
    Set-Content -LiteralPath $Sentinel -Value 'preserve' -Encoding UTF8

    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    Invoke-HiddenAndWait $Uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') 120
    if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
        throw 'Uninstall removed local application data'
    }
    Write-Host 'Installer install/smoke/uninstall/data-preservation verification passed.' `
        -ForegroundColor Green
} finally {
    $env:LOCALAPPDATA = $PriorLocalAppData
    if (Test-Path -LiteralPath $TestRoot) {
        Remove-Item -LiteralPath $TestRoot -Recurse -Force
    }
}

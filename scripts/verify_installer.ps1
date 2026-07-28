$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Python = (Resolve-Path (Join-Path $Root '.venv\Scripts\python.exe')).Path
$Installer = Join-Path $Root 'installer-output\BambooWorkbench-Setup-1.3.4.exe'
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
    Invoke-HiddenAndWait $Executable @('--initialize-install') 90
    Invoke-HiddenAndWait $Executable @('--smoke-test') 90
    Invoke-HiddenAndWait $Executable @('--demo-smoke-test') 90
    & $Python (Join-Path $Root 'scripts\verify_auto_update.py') `
        --installer $Installer --install-dir $InstallDir --version '1.3.4'
    if ($LASTEXITCODE -ne 0) {
        throw "Auto-update verification failed with exit code $LASTEXITCODE"
    }

    $PreservedDirectories = @('source', 'output', 'data', 'tasks', 'knowledge', 'module-data')
    $Sentinels = @()
    foreach ($DirectoryName in $PreservedDirectories) {
        $Directory = Join-Path $InstallDir $DirectoryName
        New-Item -ItemType Directory -Path $Directory -Force | Out-Null
        $Sentinel = Join-Path $Directory 'preserve-on-uninstall.txt'
        Set-Content -LiteralPath $Sentinel -Value 'preserve' -Encoding UTF8
        $Sentinels += $Sentinel
    }
    $Marker = Join-Path $InstallDir '.bamboo-install.json'
    if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) {
        throw 'Installed smoke test did not create the installation marker'
    }

    $Uninstaller = Join-Path $InstallDir 'unins000.exe'
    Invoke-HiddenAndWait $Uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') 120
    foreach ($Sentinel in $Sentinels) {
        if (-not (Test-Path -LiteralPath $Sentinel -PathType Leaf)) {
            throw "Uninstall removed preserved application data: $Sentinel"
        }
    }
    if (-not (Test-Path -LiteralPath $Marker -PathType Leaf)) {
        throw 'Uninstall removed the installation marker'
    }
    Write-Host 'Installer install/smoke/uninstall/install-root preservation verification passed.' `
        -ForegroundColor Green
} finally {
    $env:LOCALAPPDATA = $PriorLocalAppData
    if (Test-Path -LiteralPath $TestRoot) {
        Remove-Item -LiteralPath $TestRoot -Recurse -Force
    }
}

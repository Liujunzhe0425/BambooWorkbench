$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root

$Version = '1.3.5'
$ReleaseOutput = [System.IO.Path]::GetFullPath((Join-Path $Root 'release-output'))
$RootPrefix = $Root.TrimEnd('\') + '\'
if (-not $ReleaseOutput.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Release path escaped repository: $ReleaseOutput"
}

$PortableSource = Join-Path $Root 'dist\BambooWorkbench'
$InstallerSource = Join-Path $Root "installer-output\BambooWorkbench-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $PortableSource -PathType Container)) {
    throw 'Portable bundle does not exist. Run build_installer.ps1 first.'
}
if (-not (Test-Path -LiteralPath $InstallerSource -PathType Leaf)) {
    throw 'Installer does not exist. Run build_installer.ps1 first.'
}

if (Test-Path -LiteralPath $ReleaseOutput) {
    Remove-Item -LiteralPath $ReleaseOutput -Recurse -Force
}
New-Item -ItemType Directory -Path $ReleaseOutput -Force | Out-Null

$PortableZip = Join-Path $ReleaseOutput "BambooWorkbench-Portable-$Version.zip"
$InstallerTarget = Join-Path $ReleaseOutput "BambooWorkbench-Setup-$Version.exe"
Compress-Archive -Path (Join-Path $PortableSource '*') -DestinationPath $PortableZip `
    -CompressionLevel Optimal
Copy-Item -LiteralPath $InstallerSource -Destination $InstallerTarget

$Artifacts = @($PortableZip, $InstallerTarget)
$ChecksumLines = foreach ($Artifact in $Artifacts) {
    $Hash = (Get-FileHash -LiteralPath $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  $([System.IO.Path]::GetFileName($Artifact))"
}
$ChecksumPath = Join-Path $ReleaseOutput 'SHA256SUMS.txt'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($ChecksumPath, $ChecksumLines, $Utf8NoBom)

Write-Host "Release assets prepared: $ReleaseOutput" -ForegroundColor Green
$ChecksumLines | ForEach-Object { Write-Host $_ }

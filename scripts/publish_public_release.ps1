param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $Root 'release-output'))
$DistributionRepository = 'Liujunzhe0425/BambooWorkbench-Distribution'
$Tag = "v$Version"
$Notes = Join-Path $Root "docs\release\release-notes-$Tag.md"
$Assets = @(
    (Join-Path $ReleaseRoot "BambooWorkbench-Setup-$Version.exe"),
    (Join-Path $ReleaseRoot "BambooWorkbench-Portable-$Version.zip"),
    (Join-Path $ReleaseRoot 'SHA256SUMS.txt')
)

foreach ($Asset in $Assets) {
    if (-not (Test-Path -LiteralPath $Asset -PathType Leaf)) {
        throw "Release asset is missing: $Asset"
    }
}
if (-not (Test-Path -LiteralPath $Notes -PathType Leaf)) {
    throw "Release notes are missing: $Notes"
}

& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI is not authenticated' }
$Repository = & gh repo view $DistributionRepository --json nameWithOwner,visibility | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $Repository.visibility -ne 'PUBLIC') {
    throw 'The binary distribution repository must exist and remain public'
}

$Expected = Get-Content -LiteralPath (Join-Path $ReleaseRoot 'SHA256SUMS.txt')
foreach ($Asset in $Assets[0..1]) {
    $Name = [System.IO.Path]::GetFileName($Asset)
    $Digest = (Get-FileHash -LiteralPath $Asset -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Expected -notcontains "$Digest  $Name") {
        throw "SHA256SUMS.txt does not match $Name"
    }
}

& gh release view $Tag --repo $DistributionRepository *> $null
if ($LASTEXITCODE -eq 0) { throw "Public release already exists: $Tag" }
& gh release create $Tag @Assets `
    --repo $DistributionRepository `
    --target main `
    --title "BambooWorkbench $Tag" `
    --notes-file $Notes `
    --latest
if ($LASTEXITCODE -ne 0) { throw 'Public binary release creation failed' }

$Release = & gh api "repos/$DistributionRepository/releases/tags/$Tag" | ConvertFrom-Json
if ($Release.draft -or $Release.prerelease -or $Release.assets.Count -ne 3) {
    throw 'Public release metadata is incomplete'
}
foreach ($Asset in $Release.assets) {
    if ($Asset.state -ne 'uploaded' -or $Asset.digest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw "Public release asset is not verifiable: $($Asset.name)"
    }
}
Write-Output $Release.html_url

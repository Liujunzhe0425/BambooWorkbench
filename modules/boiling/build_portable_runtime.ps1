$ErrorActionPreference = 'Stop'

$ModuleRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $ModuleRoot '..\..'))
$RepositoryPrefix = $RepositoryRoot.TrimEnd('\') + '\'

function Assert-RepositoryChild {
    param([Parameter(Mandatory = $true)][string]$Path)
    $Resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not $Resolved.StartsWith(
        $RepositoryPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Portable runtime path escaped repository: $Resolved"
    }
    return $Resolved
}

function Remove-BuildTarget {
    param([Parameter(Mandatory = $true)][string]$Path)
    $Resolved = Assert-RepositoryChild $Path
    if (Test-Path -LiteralPath $Resolved) {
        Remove-Item -LiteralPath $Resolved -Recurse -Force
    }
}

function Invoke-IsolatedLauncher {
    param(
        [Parameter(Mandatory = $true)][string]$Launcher,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $QuotedArguments = ($Arguments | ForEach-Object {
        '"' + ([string]$_).Replace('"', '""') + '"'
    }) -join ' '
    $StartInfo.Arguments = "/d /s /c `"`"$Launcher`" $QuotedArguments`""
    $StartInfo.WorkingDirectory = Split-Path -Parent $Launcher
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    # Windows PowerShell 5 lazily initializes this collection on first access.
    $ProcessEnvironment = $StartInfo.EnvironmentVariables
    if ($null -eq $ProcessEnvironment) {
        $ProcessEnvironment = $StartInfo.EnvironmentVariables
    }
    if ($null -eq $ProcessEnvironment) {
        throw 'Unable to create the isolated process environment.'
    }
    $ProcessEnvironment['PATH'] = Join-Path $env:SystemRoot 'System32'
    $ProcessEnvironment['PATHEXT'] = '.COM;.EXE;.BAT;.CMD'
    $ProcessEnvironment['BAMBOO_PYTHON'] = ''

    $Process = [System.Diagnostics.Process]::Start($StartInfo)
    $Stdout = $Process.StandardOutput.ReadToEnd()
    $Stderr = $Process.StandardError.ReadToEnd()
    $Process.WaitForExit()
    return [pscustomobject]@{
        ExitCode = $Process.ExitCode
        Stdout = $Stdout
        Stderr = $Stderr
    }
}

$BuildRoot = Assert-RepositoryChild (Join-Path $RepositoryRoot 'build\boiling-runtime')
$VerificationRoot = Assert-RepositoryChild (
    Join-Path $RepositoryRoot 'build\boiling-runtime-verification'
)
$PortableModule = Assert-RepositoryChild (
    Join-Path $RepositoryRoot 'dist\BambooWorkbench\modules\boiling'
)
$RuntimeRoot = Assert-RepositoryChild (Join-Path $PortableModule 'runtime')

Remove-BuildTarget $BuildRoot
Remove-BuildTarget $VerificationRoot
Remove-BuildTarget $RuntimeRoot
New-Item -ItemType Directory -Force -Path $BuildRoot, $VerificationRoot, $RuntimeRoot |
    Out-Null

$VenvPython = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
$Python = if (
    $env:BAMBOO_PYTHON -and
    (Test-Path -LiteralPath $env:BAMBOO_PYTHON -PathType Leaf)
) {
    $env:BAMBOO_PYTHON
} elseif (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
    $VenvPython
} else {
    'python'
}

& $Python -c 'import PyInstaller'
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller is required; run the repository portable build or install .[packaging].'
}

& $Python -m PyInstaller --clean --noconfirm --onefile `
    --name boiling_module `
    --workpath $BuildRoot `
    --specpath $BuildRoot `
    --distpath $RuntimeRoot `
    (Join-Path $ModuleRoot 'src\boiling_module.py')
if ($LASTEXITCODE -ne 0) {
    throw "Boiling portable runtime build failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path (Join-Path $PortableModule 'rules') | Out-Null
Copy-Item -LiteralPath (Join-Path $ModuleRoot 'module.json') -Destination $PortableModule -Force
Copy-Item -LiteralPath (Join-Path $ModuleRoot 'run_module.bat') -Destination $PortableModule -Force
Copy-Item -LiteralPath (Join-Path $ModuleRoot 'rules\default_rules.yaml') `
    -Destination (Join-Path $PortableModule 'rules\default_rules.yaml') -Force

$Launcher = Join-Path $PortableModule 'run_module.bat'
foreach ($Command in @('version', 'self-check')) {
    $Run = Invoke-IsolatedLauncher -Launcher $Launcher -Arguments @($Command)
    if ($Run.ExitCode -ne 0) {
        throw "Packaged boiling $Command failed with exit code $($Run.ExitCode): $($Run.Stderr)"
    }
    if ($Run.Stderr.Trim()) {
        throw "Packaged boiling $Command wrote diagnostics: $($Run.Stderr)"
    }
}

$Sample = Join-Path $ModuleRoot 'tests\fixtures\samples\input\02_density_observation.xlsx'
$DraftOutput = Join-Path $VerificationRoot 'draft-output'
$FinalOutput = Join-Path $VerificationRoot 'final-output'
$DraftJobPath = Join-Path $VerificationRoot 'job-draft.json'
$FinalJobPath = Join-Path $VerificationRoot 'job-finalize.json'
$ConfirmationPath = Join-Path $VerificationRoot 'confirmation.json'
$DraftJob = [ordered]@{
    schema_version = '1.0'
    job_id = 'PORTABLE-DRAFT-001'
    module_id = 'boiling'
    phase = 'draft'
    run_mode = 'single'
    input_files = @($Sample)
    output_dir = $DraftOutput
    module_config_file = $null
    ai_enabled = $false
    task_name = 'Boiling portable validation 2026-01'
    period_year = 2026
    period_month = 1
    learning_enabled = $true
    allowed_knowledge_scopes = @()
    parent_job_id = $null
    confirmation_file = $null
    service_response_file = $null
}
$DraftJob | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $DraftJobPath -Encoding UTF8
$DraftRun = Invoke-IsolatedLauncher -Launcher $Launcher -Arguments @('run', '--job', $DraftJobPath)
if ($DraftRun.ExitCode -ne 0) {
    throw "Packaged boiling draft failed with exit code $($DraftRun.ExitCode): $($DraftRun.Stderr)"
}
$DraftResult = Get-Content -LiteralPath (Join-Path $DraftOutput 'result.json') -Raw -Encoding UTF8 |
    ConvertFrom-Json
if ($DraftResult.status -ne 'needs_confirmation' -or $DraftResult.confirmations.Count -lt 1) {
    throw 'Packaged boiling draft did not produce the expected confirmation round.'
}
$Answers = @($DraftResult.confirmations | ForEach-Object {
    $Value = if ($_.options.Count -gt 0) { $_.options[0] } else { $_.suggested_value }
    [ordered]@{
        confirmation_id = $_.confirmation_id
        value = $Value
        apply_to_batch = $false
        remember_mapping = $false
    }
})
[ordered]@{
    schema_version = '1.0'
    job_id = 'PORTABLE-DRAFT-001'
    answers = $Answers
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ConfirmationPath -Encoding UTF8
$FinalJob = [ordered]@{}
foreach ($Key in $DraftJob.Keys) {
    $FinalJob[$Key] = $DraftJob[$Key]
}
$FinalJob.job_id = 'PORTABLE-FINAL-001'
$FinalJob.phase = 'finalize'
$FinalJob.output_dir = $FinalOutput
$FinalJob.parent_job_id = 'PORTABLE-DRAFT-001'
$FinalJob.confirmation_file = $ConfirmationPath
$FinalJob | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $FinalJobPath -Encoding UTF8
$FinalRun = Invoke-IsolatedLauncher -Launcher $Launcher -Arguments @('run', '--job', $FinalJobPath)
if ($FinalRun.ExitCode -ne 0) {
    throw "Packaged boiling finalize failed with exit code $($FinalRun.ExitCode): $($FinalRun.Stderr)"
}
$FinalResult = Get-Content -LiteralPath (Join-Path $FinalOutput 'result.json') -Raw -Encoding UTF8 |
    ConvertFrom-Json
if (
    $FinalResult.status -notin @('success', 'partial_success') -or
    $FinalResult.confirmations.Count -ne 0
) {
    throw 'Packaged boiling finalize did not reach a confirmation-free terminal result.'
}
foreach ($Artifact in @('boiling_summary.xlsx', 'boiling_analysis.md', 'boiling_records.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $FinalOutput $Artifact) -PathType Leaf)) {
        throw "Packaged boiling finalize did not create $Artifact"
    }
}

$SnapshotSource = Join-Path $FinalOutput 'boiling_monthly_snapshot.json'
if (-not (Test-Path -LiteralPath $SnapshotSource -PathType Leaf)) {
    throw 'Packaged boiling finalize did not create boiling_monthly_snapshot.json'
}
if (
    $null -eq $FinalResult.monthly_snapshot -or
    $FinalResult.monthly_snapshot.path -ne $SnapshotSource -or
    $FinalResult.monthly_snapshot.year -ne 2026 -or
    $FinalResult.monthly_snapshot.month -ne 1
) {
    throw 'Packaged boiling finalize did not publish the expected monthly_snapshot reference.'
}
if (@($FinalResult.outputs | Where-Object {
    $_.type -in @('monthly_snapshot', 'confirmation_learning')
}).Count -ne 0) {
    throw 'Packaged boiling finalize published internal artifacts as ordinary outputs.'
}
$Snapshot = Get-Content -LiteralPath $SnapshotSource -Raw -Encoding UTF8 | ConvertFrom-Json
$SnapshotRoot = Join-Path $VerificationRoot 'snapshots'
$RollupOutput = Join-Path $VerificationRoot 'rollup-output'
$RollupRequestPath = Join-Path $VerificationRoot 'rollup-request.json'
$RollupResponsePath = Join-Path $RollupOutput 'rollup-response.json'
New-Item -ItemType Directory -Force -Path $SnapshotRoot, $RollupOutput | Out-Null
$CandidateSnapshot = Join-Path $SnapshotRoot (
    '{0:D4}-{1:D2}.json' -f [int]$Snapshot.year, [int]$Snapshot.month
)
Copy-Item -LiteralPath $SnapshotSource -Destination $CandidateSnapshot -Force
$SnapshotHash = (Get-FileHash -LiteralPath $CandidateSnapshot -Algorithm SHA256).Hash.ToLowerInvariant()
$RuleHash = (
    Get-FileHash -LiteralPath (Join-Path $ModuleRoot 'rules\default_rules.yaml') -Algorithm SHA256
).Hash.ToLowerInvariant()
[ordered]@{
    schema_version = '1.0'
    transaction_id = 'PORTABLE-ROLLUP-001'
    module_id = 'boiling'
    module_version = '1.3.5'
    year = [int]$Snapshot.year
    target_month = [int]$Snapshot.month
    snapshot_root = $SnapshotRoot
    output_dir = $RollupOutput
    snapshots = @([ordered]@{
        snapshot_id = 'PORTABLE-SNAPSHOT-001'
        job_id = 'PORTABLE-FINAL-001'
        module_id = 'boiling'
        year = [int]$Snapshot.year
        month = [int]$Snapshot.month
        path = $CandidateSnapshot
        size = (Get-Item -LiteralPath $CandidateSnapshot).Length
        sha256 = $SnapshotHash
    })
    configuration_identity = [ordered]@{
        version = $Snapshot.payload.rule_version
        sha256 = $RuleHash
    }
    offline_required = $true
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $RollupRequestPath -Encoding UTF8
$RollupRun = Invoke-IsolatedLauncher -Launcher $Launcher -Arguments @(
    'rollup',
    '--request',
    $RollupRequestPath,
    '--response',
    $RollupResponsePath
)
if ($RollupRun.ExitCode -ne 0) {
    throw "Packaged boiling rollup failed with exit code $($RollupRun.ExitCode): $($RollupRun.Stderr)"
}
$RollupResponse = Get-Content -LiteralPath $RollupResponsePath -Raw -Encoding UTF8 |
    ConvertFrom-Json
if (
    $RollupResponse.status -ne 'success' -or
    $RollupResponse.transaction_id -ne 'PORTABLE-ROLLUP-001' -or
    $RollupResponse.module_version -ne '1.3.5' -or
    $RollupResponse.network_call_count -ne 0 -or
    $RollupResponse.record_count -lt 1 -or
    $RollupResponse.used_months.Count -ne 1 -or
    $RollupResponse.used_months[0] -ne [int]$Snapshot.month -or
    $RollupResponse.snapshot_hashes.Count -ne 1 -or
    $RollupResponse.snapshot_hashes[0].snapshot_id -ne 'PORTABLE-SNAPSHOT-001' -or
    $RollupResponse.snapshot_hashes[0].sha256 -ne $SnapshotHash
) {
    throw 'Packaged boiling rollup response did not satisfy the offline monthly contract.'
}
foreach ($Artifact in @(
    'boiling_summary.xlsx',
    'boiling_analysis.xlsx',
    'boiling_analysis.md',
    'boiling_records.json'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $RollupOutput $Artifact) -PathType Leaf)) {
        throw "Packaged boiling rollup did not create $Artifact"
    }
}

Write-Host 'Boiling standalone portable runtime built and verified.' -ForegroundColor Green

$ErrorActionPreference = 'Stop'

$ModuleRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $ModuleRoot '..\..'))
$PortableRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $RepoRoot 'dist\BambooWorkbench')
)
$PortablePrefix = $PortableRoot.TrimEnd('\') + '\'
$ModuleDestination = [System.IO.Path]::GetFullPath(
    (Join-Path $PortableRoot 'modules\after_sales')
)
if (-not $ModuleDestination.StartsWith($PortablePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Portable module path escaped bundle: $ModuleDestination"
}
if (-not (Test-Path -LiteralPath (Join-Path $ModuleDestination 'module.json') -PathType Leaf)) {
    throw 'Build the BambooWorkbench portable bundle before installing the after-sales runtime.'
}

$BuildRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $RepoRoot 'build\after_sales_runtime')
)
$BuildPrefix = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot 'build')).TrimEnd('\') + '\'
if (-not $BuildRoot.StartsWith($BuildPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Runtime build path escaped repository build directory: $BuildRoot"
}
if (Test-Path -LiteralPath $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $BuildRoot 'spec') -Force | Out-Null
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot 'pyinstaller-cache'
$env:TEMP = Join-Path $BuildRoot 'temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:PYINSTALLER_CONFIG_DIR -Force | Out-Null
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null

$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python is missing: $Python"
}

& $Python -m PyInstaller --noconfirm --clean --onedir `
    --name after_sales_agent `
    --paths (Join-Path $ModuleRoot 'src') `
    --workpath (Join-Path $BuildRoot 'work') `
    --distpath (Join-Path $BuildRoot 'dist') `
    --specpath (Join-Path $BuildRoot 'spec') `
    (Join-Path $ModuleRoot 'src\after_sales_agent\cli.py')
if ($LASTEXITCODE -ne 0) {
    throw "After-sales runtime build failed with exit code $LASTEXITCODE"
}

$RuntimeSource = Join-Path $BuildRoot 'dist\after_sales_agent'
$RuntimeDestination = Join-Path $ModuleDestination 'runtime'
$RuntimeDestination = [System.IO.Path]::GetFullPath($RuntimeDestination)
$ModulePrefix = $ModuleDestination.TrimEnd('\') + '\'
if (-not $RuntimeDestination.StartsWith($ModulePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Runtime destination escaped after-sales module: $RuntimeDestination"
}
if (Test-Path -LiteralPath $RuntimeDestination) {
    Remove-Item -LiteralPath $RuntimeDestination -Recurse -Force
}
Copy-Item -LiteralPath $RuntimeSource -Destination $RuntimeDestination -Recurse

$RuntimeExe = Join-Path $RuntimeDestination 'after_sales_agent.exe'
& $RuntimeExe version
if ($LASTEXITCODE -ne 0) {
    throw "Packaged after-sales runtime version check failed: $LASTEXITCODE"
}
& $RuntimeExe self-check
if ($LASTEXITCODE -ne 0) {
    throw "Packaged after-sales runtime self-check failed: $LASTEXITCODE"
}

# The desktop host decodes every progress line as strict UTF-8. Validate the
# actual frozen executable because Windows console code pages can differ from
# the source-Python test environment.
$ValidationOutput = Join-Path $BuildRoot 'protocol-validation-output'
$ValidationJobPath = Join-Path $BuildRoot 'protocol-validation-job.json'
$ValidationInput = Join-Path $ModuleRoot 'tests\fixtures\samples\input\sample_after_sales.xlsx'
$ValidationJob = [ordered]@{
    schema_version = '1.0'
    job_id = 'portable-protocol-validation'
    module_id = 'after_sales'
    phase = 'draft'
    run_mode = 'batch'
    input_files = @($ValidationInput)
    output_dir = $ValidationOutput
}
$ValidationJobJson = $ValidationJob | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText(
    $ValidationJobPath,
    $ValidationJobJson,
    [System.Text.UTF8Encoding]::new($false)
)
& $Python (Join-Path $ModuleRoot 'scripts\verify_portable_runtime.py') `
    $RuntimeExe $ValidationJobPath
if ($LASTEXITCODE -ne 0) {
    throw "Packaged after-sales runtime protocol check failed: $LASTEXITCODE"
}

Write-Host "After-sales portable runtime installed: $RuntimeDestination" -ForegroundColor Green

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Bundle = [System.IO.Path]::GetFullPath((Join-Path $Root 'dist\BambooWorkbench'))
if (-not $Bundle.StartsWith($Root.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Portable bundle escaped repository'
}

$Required = @(
    'BambooWorkbench.exe',
    'BambooModuleHost.exe',
    'contracts\schemas\module-manifest.schema.json',
    'assets\brand\team-logo.svg',
    'logo\team-logo.png',
    'logo\BambooWorkbench.ico',
    'resources\themes\bamboo.qss',
    'mock_modules\moisture\module.json',
    'mock_modules\boiling\module.json',
    'mock_modules\after_sales\module.json'
)
foreach ($Item in $Required) {
    if (-not (Test-Path -LiteralPath (Join-Path $Bundle $Item) -PathType Leaf)) {
        throw "Missing packaged file: $Item"
    }
}

$SourceModules = Join-Path $Root 'modules'
if (Test-Path -LiteralPath $SourceModules -PathType Container) {
    Get-ChildItem -LiteralPath $SourceModules -Directory | ForEach-Object {
        $Manifest = "modules\$($_.Name)\module.json"
        $PackagedManifest = Join-Path $Bundle $Manifest
        if (-not (Test-Path -LiteralPath $PackagedManifest -PathType Leaf)) {
            throw "Missing packaged real module: $Manifest"
        }

        $ModuleData = Get-Content -LiteralPath $PackagedManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        $Launcher = Join-Path (Split-Path -Parent $PackagedManifest) $ModuleData.entrypoint
        if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
            throw "Missing packaged module launcher: $Launcher"
        }

        foreach ($Command in @('version', 'self-check')) {
            $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
            $StartInfo.FileName = Join-Path $env:SystemRoot 'System32\cmd.exe'
            $StartInfo.Arguments = "/d /s /c `"`"$Launcher`" $Command`""
            $StartInfo.WorkingDirectory = Split-Path -Parent $Launcher
            $StartInfo.UseShellExecute = $false
            $StartInfo.CreateNoWindow = $true
            $StartInfo.RedirectStandardOutput = $true
            $StartInfo.RedirectStandardError = $true
            $StartInfo.Environment.Clear()
            $StartInfo.Environment['SystemRoot'] = $env:SystemRoot
            $StartInfo.Environment['ComSpec'] = Join-Path $env:SystemRoot 'System32\cmd.exe'
            $StartInfo.Environment['PATH'] = Join-Path $env:SystemRoot 'System32'
            $StartInfo.Environment['PATHEXT'] = '.COM;.EXE;.BAT;.CMD'
            $StartInfo.Environment['TEMP'] = $env:TEMP
            $StartInfo.Environment['TMP'] = $env:TMP

            $Process = [System.Diagnostics.Process]::Start($StartInfo)
            $Stdout = $Process.StandardOutput.ReadToEnd()
            $Stderr = $Process.StandardError.ReadToEnd()
            $Process.WaitForExit()
            if ($Process.ExitCode -ne 0) {
                throw "Packaged module '$($ModuleData.module_id)' $Command failed with exit code $($Process.ExitCode): $Stderr"
            }
            if ($Stderr.Trim()) {
                throw "Packaged module '$($ModuleData.module_id)' $Command wrote diagnostics: $Stderr"
            }
            if ($Command -eq 'version' -and $Stdout.Trim() -ne [string]$ModuleData.version) {
                throw "Packaged module '$($ModuleData.module_id)' reported version '$($Stdout.Trim())', expected '$($ModuleData.version)'."
            }
        }
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
Write-Host 'Portable bundle verification passed.' -ForegroundColor Green

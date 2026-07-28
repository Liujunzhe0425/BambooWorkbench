from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .service import UpdateError

_HELPER = r'''param(
  [Parameter(Mandatory=$true)][int]$ParentPid,
  [Parameter(Mandatory=$true)][string]$InstallerPath,
  [Parameter(Mandatory=$true)][string]$ApplicationPath,
  [Parameter(Mandatory=$true)][string]$InstallDirectory,
  [Parameter(Mandatory=$true)][string]$ExpectedVersion,
  [Parameter(Mandatory=$true)][string]$LogPath,
  [Parameter(Mandatory=$true)]
  [ValidateSet('normal','smoke-test')]
  [string]$RestartMode
)
$ErrorActionPreference = 'Stop'
function Write-UpdateLog([string]$Message) {
  $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
  Add-Content -LiteralPath $LogPath -Value "$timestamp $Message" -Encoding UTF8
}
try {
  Write-UpdateLog "helper started parent=$ParentPid version=$ExpectedVersion"
  Wait-Process -Id $ParentPid -Timeout 120 -ErrorAction SilentlyContinue
  if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
    throw 'application did not exit within 120 seconds'
  }
  $innoLog = Join-Path (Split-Path -Parent $LogPath) 'inno-setup.log'
  $arguments = @(
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/CLOSEAPPLICATIONS',
    '/FORCECLOSEAPPLICATIONS',
    '/NORESTART',
    "/DIR=`"$InstallDirectory`"",
    "/LOG=`"$innoLog`""
  )
  Write-UpdateLog "installer starting"
  $installer = Start-Process -FilePath $InstallerPath -ArgumentList $arguments `
    -PassThru -Wait -WindowStyle Hidden
  Write-UpdateLog "installer exited code=$($installer.ExitCode)"
  if ($installer.ExitCode -ne 0) { throw "installer failed with code $($installer.ExitCode)" }
  foreach ($relative in @(
    'modules\moisture\module.json',
    'modules\boiling\module.json',
    'modules\after_sales\module.json'
  )) {
    $manifestPath = Join-Path $InstallDirectory $relative
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
      throw "installed manifest is missing: $relative"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$manifest.module_version -ne $ExpectedVersion) {
      throw "installed version mismatch: $relative"
    }
  }
  if (-not (Test-Path -LiteralPath $ApplicationPath -PathType Leaf)) {
    throw 'installed application executable is missing'
  }
  if ($RestartMode -eq 'smoke-test') {
    $application = Start-Process -FilePath $ApplicationPath -ArgumentList '--smoke-test' `
      -PassThru -Wait -WindowStyle Hidden
    if ($application.ExitCode -ne 0) {
      throw "restarted application smoke test failed with code $($application.ExitCode)"
    }
    Write-UpdateLog 'application smoke restart completed'
  } else {
    $application = Start-Process -FilePath $ApplicationPath -PassThru -WindowStyle Normal
    Write-UpdateLog "application restarted pid=$($application.Id)"
  }
  exit 0
} catch {
  Write-UpdateLog "update failed: $($_.Exception.Message)"
  if (Test-Path -LiteralPath $ApplicationPath -PathType Leaf) {
    try {
      $application = Start-Process -FilePath $ApplicationPath -PassThru -WindowStyle Normal
      Write-UpdateLog "existing application reopened pid=$($application.Id)"
    } catch {
      Write-UpdateLog "application reopen failed: $($_.Exception.Message)"
    }
  }
  exit 1
}
'''

_INSTALLER_NAME = re.compile(r"^BambooWorkbench-Setup-(\d+\.\d+\.\d+)\.exe$")


def launch_installer_after_exit(
    installer: Path,
    helper_directory: Path,
    *,
    parent_pid: int | None = None,
    application_path: Path | None = None,
    install_directory: Path | None = None,
    expected_version: str | None = None,
    restart_mode: str = "normal",
) -> subprocess.Popen[bytes]:
    if sys.platform != "win32":
        raise UpdateError("自动安装更新当前仅支持 Windows")
    installer = installer.resolve(strict=True)
    match = _INSTALLER_NAME.fullmatch(installer.name)
    if not installer.is_file() or match is None:
        raise UpdateError("待安装的更新文件无效")
    target_application = (application_path or Path(sys.executable)).resolve(strict=True)
    target_install_directory = (
        install_directory or target_application.parent
    ).resolve(strict=True)
    if (
        not target_install_directory.is_dir()
        or target_application.parent != target_install_directory
    ):
        raise UpdateError("当前安装目录无效")
    version = expected_version or match.group(1)
    if version != match.group(1):
        raise UpdateError("安装包版本与目标版本不一致")
    if restart_mode not in {"normal", "smoke-test"}:
        raise UpdateError("更新重启模式无效")
    helper_directory = helper_directory.resolve()
    helper_directory.mkdir(parents=True, exist_ok=True)
    staged_installer = (helper_directory / installer.name).resolve()
    helper = (helper_directory / "install-update.ps1").resolve()
    log_path = (helper_directory / "update-install.log").resolve()
    if (
        helper.parent != helper_directory
        or staged_installer.parent != helper_directory
        or log_path.parent != helper_directory
    ):
        raise UpdateError("更新辅助程序路径无效")
    if staged_installer != installer:
        shutil.copy2(installer, staged_installer)
    helper.write_text(_HELPER, encoding="utf-8", newline="\n")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        return subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                "-ParentPid",
                str(parent_pid or os.getpid()),
                "-InstallerPath",
                str(staged_installer),
                "-ApplicationPath",
                str(target_application),
                "-InstallDirectory",
                str(target_install_directory),
                "-ExpectedVersion",
                version,
                "-LogPath",
                str(log_path),
                "-RestartMode",
                restart_mode,
            ],
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as error:
        raise UpdateError("无法启动更新安装程序") from error

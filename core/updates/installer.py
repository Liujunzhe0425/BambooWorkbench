from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .service import UpdateError

_HELPER = r'''param(
  [Parameter(Mandatory=$true)][int]$ParentPid,
  [Parameter(Mandatory=$true)][string]$InstallerPath,
  [Parameter(Mandatory=$true)][string]$ApplicationPath
)
$ErrorActionPreference = 'Stop'
Wait-Process -Id $ParentPid -Timeout 120 -ErrorAction SilentlyContinue
$installer = Start-Process -FilePath $InstallerPath -ArgumentList @(
  '/SILENT', '/SUPPRESSMSGBOXES', '/CLOSEAPPLICATIONS', '/NORESTART'
) -PassThru -Wait -WindowStyle Hidden
if ($installer.ExitCode -ne 0) { exit $installer.ExitCode }
if (Test-Path -LiteralPath $ApplicationPath -PathType Leaf) {
  Start-Process -FilePath $ApplicationPath -WindowStyle Normal
}
'''


def launch_installer_after_exit(
    installer: Path,
    helper_directory: Path,
    *,
    parent_pid: int | None = None,
    application_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    if sys.platform != "win32":
        raise UpdateError("自动安装更新当前仅支持 Windows")
    installer = installer.resolve(strict=True)
    if not installer.is_file() or installer.suffix.casefold() != ".exe":
        raise UpdateError("待安装的更新文件无效")
    target_application = (application_path or Path(sys.executable)).resolve(strict=True)
    helper_directory = helper_directory.resolve()
    helper_directory.mkdir(parents=True, exist_ok=True)
    helper = (helper_directory / "install-update.ps1").resolve()
    if helper.parent != helper_directory:
        raise UpdateError("更新辅助程序路径无效")
    helper.write_text(_HELPER, encoding="utf-8", newline="\n")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "DETACHED_PROCESS", 0
    )
    try:
        return subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(helper),
                "-ParentPid",
                str(parent_pid or os.getpid()),
                "-InstallerPath",
                str(installer),
                "-ApplicationPath",
                str(target_application),
            ],
            close_fds=True,
            creationflags=creation_flags,
        )
    except OSError as error:
        raise UpdateError("无法启动更新安装程序") from error

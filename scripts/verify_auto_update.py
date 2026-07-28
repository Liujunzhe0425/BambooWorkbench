from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from core.updates.installer import launch_installer_after_exit

MODULE_IDS = ("moisture", "boiling", "after_sales")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the packaged auto-update flow")
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    installer = args.installer.resolve(strict=True)
    install_directory = args.install_dir.resolve(strict=True)
    application = (install_directory / "BambooWorkbench.exe").resolve(strict=True)

    parent = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        close_fds=True,
    )
    helper_directory = Path(
        tempfile.mkdtemp(prefix="BambooWorkbench-updater-test-")
    ).resolve()
    try:
        helper = launch_installer_after_exit(
            installer,
            helper_directory,
            parent_pid=parent.pid,
            application_path=application,
            install_directory=install_directory,
            expected_version=args.version,
            restart_mode="smoke-test",
        )
        try:
            exit_code = helper.wait(timeout=300)
        except subprocess.TimeoutExpired:
            helper.kill()
            raise RuntimeError("auto-update helper timed out after 300 seconds") from None
        if exit_code != 0:
            log_path = helper_directory / "update-install.log"
            details = log_path.read_text(encoding="utf-8-sig") if log_path.exists() else ""
            raise RuntimeError(f"auto-update helper failed with code {exit_code}\n{details}")

        log_path = helper_directory / "update-install.log"
        if not log_path.exists():
            raise RuntimeError(
                "auto-update helper created no log; retained diagnostics at "
                f"{helper_directory}"
            )
        log_text = log_path.read_text(encoding="utf-8-sig")
        required_log_entries = (
            "installer exited code=0",
            "application smoke restart completed",
        )
        for entry in required_log_entries:
            if entry not in log_text:
                raise RuntimeError(f"auto-update log entry is missing: {entry}")
    except Exception:
        print(f"Retained auto-update diagnostics: {helper_directory}", file=sys.stderr)
        raise
    else:
        shutil.rmtree(helper_directory)

    for module_id in MODULE_IDS:
        manifest_path = install_directory / "modules" / module_id / "module.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("module_version") != args.version:
            raise RuntimeError(f"installed module version mismatch: {module_id}")

    print("Auto-update overwrite/install/restart verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

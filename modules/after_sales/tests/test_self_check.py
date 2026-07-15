import os
import subprocess
import sys
from pathlib import Path


def test_self_check_runs():
    module_dir = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [str(module_dir / "run_module.bat"), "self-check"],
        cwd=module_dir,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr


def test_module_launcher_reports_version():
    if os.name != "nt":
        return
    module_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update({"PYTHON_EXE": sys.executable})
    completed = subprocess.run(
        [str(module_dir / "run_module.bat"), "version"],
        cwd=module_dir,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "after_sales 1.3.1"

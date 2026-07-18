import os
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))

from after_sales_agent import cli as module_cli  # noqa: E402


def test_self_check_runs():
    completed = subprocess.run(
        [str(MODULE_DIR / "run_module.bat"), "self-check"],
        cwd=MODULE_DIR,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr


def test_module_launcher_reports_version():
    if os.name != "nt":
        return
    env = os.environ.copy()
    env.update({"PYTHON_EXE": sys.executable})
    completed = subprocess.run(
        [str(MODULE_DIR / "run_module.bat"), "version"],
        cwd=MODULE_DIR,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "after_sales 1.3.1"


def test_frozen_module_root_resolves_to_portable_module(monkeypatch):
    executable = MODULE_DIR / "runtime" / "after_sales_agent.exe"
    monkeypatch.setattr(module_cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(module_cli.sys, "executable", str(executable))

    assert module_cli._module_root() == MODULE_DIR


def test_launcher_prefers_bundled_runtime_before_external_python():
    launcher = (MODULE_DIR / "run_module.bat").read_text(encoding="utf-8")

    runtime_position = launcher.index("runtime\\after_sales_agent.exe")
    python_position = launcher.index("if defined PYTHON_EXE")
    assert runtime_position < python_position

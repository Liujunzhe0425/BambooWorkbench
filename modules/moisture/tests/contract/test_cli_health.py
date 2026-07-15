import os
import re
import subprocess
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = MODULE_ROOT / "run_module.bat"


def run_cli(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHER), *arguments],
        cwd=MODULE_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_version_writes_only_semver_to_stdout() -> None:
    completed = run_cli("version")

    assert completed.returncode == 0
    assert re.fullmatch(r"\d+\.\d+\.\d+\n", completed.stdout)
    assert completed.stderr == ""


def test_self_check_uses_stderr_for_diagnostics() -> None:
    completed = run_cli("self-check")

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert "self-check: ok" in completed.stderr


def test_unknown_command_returns_cli_error() -> None:
    completed = run_cli("run")

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr


def test_top_level_help_returns_cli_error_without_stdout() -> None:
    completed = run_cli("--help")

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr


def test_command_help_returns_cli_error_without_stdout() -> None:
    completed = run_cli("version", "--help")

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr


def test_missing_python_runtime_returns_environment_error() -> None:
    env = os.environ.copy()
    env.pop("BAMBOO_MODULE_PYTHON", None)
    env["PATH"] = ""

    completed = run_cli("self-check", env=env)

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "Python" in completed.stderr

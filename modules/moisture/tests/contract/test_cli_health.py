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


def test_explicit_python_without_schema_dependency_is_not_launched(tmp_path: Path) -> None:
    fake_python = tmp_path / "python-without-jsonschema.cmd"
    fake_python.write_text(
        "@echo off\n"
        'if "%~1"=="-c" exit /b 90\n'
        'if "%~1"=="-m" exit /b 91\n'
        "exit /b 92\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["BAMBOO_MODULE_PYTHON"] = str(fake_python)

    completed = run_cli("self-check", env=env)

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "jsonschema" in completed.stderr


def test_explicit_missing_python_runtime_returns_environment_error(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["BAMBOO_MODULE_PYTHON"] = str(tmp_path / "missing-python.exe")

    completed = run_cli("self-check", env=env)

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "Python" in completed.stderr


def test_launcher_probes_declared_schema_dependency() -> None:
    launcher_text = LAUNCHER.read_text(encoding="utf-8")

    assert "import jsonschema" in launcher_text


def test_isolated_launcher_without_dependency_ready_python_returns_4(
    tmp_path: Path,
) -> None:
    isolated_launcher = tmp_path / LAUNCHER.name
    isolated_launcher.write_bytes(LAUNCHER.read_bytes())
    env = os.environ.copy()
    env.pop("BAMBOO_MODULE_PYTHON", None)
    env["PATH"] = ""

    completed = subprocess.run(
        [str(isolated_launcher), "version"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "jsonschema" in completed.stderr

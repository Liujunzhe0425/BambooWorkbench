import json
import os
import re
import subprocess
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
REPOSITORY_PYTHON = REPOSITORY_ROOT / ".venv" / "Scripts" / "python.exe"
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


def run_isolated_cli(
    launcher: Path,
    *arguments: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    command_processor = Path(env["SYSTEMROOT"]) / "System32" / "cmd.exe"
    return subprocess.run(
        [str(command_processor), "/d", "/c", str(launcher), *arguments],
        cwd=launcher.parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def write_fake_python_runtime(
    directory: Path,
    name: str,
    *,
    supported: bool,
) -> Path:
    driver = directory / f"{name}-driver.py"
    driver.write_text(
        "import os\n"
        "import pathlib\n"
        "import sys\n"
        "\n"
        "arguments = sys.argv[1:]\n"
        "if arguments and arguments[0] in {'-3.12', '-3'}:\n"
        "    arguments = arguments[1:]\n"
        "if arguments and arguments[0] == '-c':\n"
        "    probe = arguments[1]\n"
        "    if 'sys.version_info' in probe and 'import jsonschema' in probe:\n"
        f"        raise SystemExit({0 if supported else 90})\n"
        "    if probe.strip() == 'import jsonschema':\n"
        "        raise SystemExit(0)\n"
        "    raise SystemExit(92)\n"
        "if arguments and arguments[0] == '-m':\n"
        "    marker = os.environ.get('SHIM_LAUNCH_MARKER')\n"
        "    if marker:\n"
        "        pathlib.Path(marker).write_text('launched', encoding='utf-8')\n"
        f"    if {supported!r} and arguments[1:] == ['moisture.cli', 'version']:\n"
        "        print('0.1.0')\n"
        "        raise SystemExit(0)\n"
        "    raise SystemExit(91)\n"
        "raise SystemExit(93)\n",
        encoding="utf-8",
    )
    shim = directory / name
    shim.write_text(
        "@echo off\n"
        f'"%FAKE_PYTHON_DRIVER%" "{driver}" %*\n'
        "exit /b %ERRORLEVEL%\n",
        encoding="utf-8",
    )
    return shim


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


def test_explicit_python_below_3_11_is_not_launched(tmp_path: Path) -> None:
    marker = tmp_path / "explicit-module-launched.txt"
    fake_python = write_fake_python_runtime(
        tmp_path,
        "python-3.10.cmd",
        supported=False,
    )
    env = os.environ.copy()
    env["BAMBOO_MODULE_PYTHON"] = str(fake_python)
    env["FAKE_PYTHON_DRIVER"] = str(REPOSITORY_PYTHON)
    env["SHIM_LAUNCH_MARKER"] = str(marker)

    completed = run_cli("version", env=env)

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "Python" in completed.stderr
    assert "3.11" in completed.stderr
    assert not marker.exists()


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
    assert "sys.version_info" in launcher_text
    assert "(3, 11)" in launcher_text


def test_launcher_never_selects_python_from_path() -> None:
    launcher_text = LAUNCHER.read_text(encoding="utf-8")

    assert "where.exe" not in launcher_text
    assert ":path_python" not in launcher_text
    assert not re.search(r"(?im)^\s*(?:call\s+)?python(?:\.exe)?\s", launcher_text)
    assert not re.search(r"(?im)^\s*(?:call\s+)?py\s+-", launcher_text)


def test_launcher_prefers_active_environment_before_repository_and_module_venvs() -> None:
    launcher_text = LAUNCHER.read_text(encoding="utf-8")

    active_environment = launcher_text.index("if defined VIRTUAL_ENV")
    repository_environment = launcher_text.index(r"..\..\.venv\Scripts\python.exe")
    module_environment = launcher_text.index(r"%~dp0.venv\Scripts\python.exe")
    assert active_environment < repository_environment < module_environment


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


def test_dependency_ready_path_python_is_never_probed_or_launched(tmp_path: Path) -> None:
    isolated_root = tmp_path / "isolated"
    isolated_root.mkdir()
    isolated_launcher = isolated_root / LAUNCHER.name
    isolated_launcher.write_bytes(LAUNCHER.read_bytes())
    shims = tmp_path / "shims"
    shims.mkdir()
    marker = tmp_path / "python-module-launched.txt"
    write_fake_python_runtime(shims, "python.cmd", supported=True)
    write_fake_python_runtime(shims, "py.cmd", supported=True)
    env = os.environ.copy()
    env.pop("BAMBOO_MODULE_PYTHON", None)
    env.pop("VIRTUAL_ENV", None)
    env["PATH"] = str(shims)
    env["FAKE_PYTHON_DRIVER"] = str(REPOSITORY_PYTHON)
    env["SHIM_LAUNCH_MARKER"] = str(marker)

    completed = run_isolated_cli(isolated_launcher, "version", env=env)

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "jsonschema" in completed.stderr
    assert not marker.exists()


def test_invalid_active_environment_does_not_fall_back_to_repository_venv(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env.pop("BAMBOO_MODULE_PYTHON", None)
    env["VIRTUAL_ENV"] = str(tmp_path / "missing-environment")

    completed = run_cli("version", env=env)

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "VIRTUAL_ENV" in completed.stderr


def test_active_repository_environment_runs_all_contract_commands(tmp_path: Path) -> None:
    repository_environment = REPOSITORY_ROOT / ".venv"
    env = os.environ.copy()
    env.pop("BAMBOO_MODULE_PYTHON", None)
    env["VIRTUAL_ENV"] = str(repository_environment)

    version = run_cli("version", env=env)
    self_check = run_cli("self-check", env=env)

    job_dir = tmp_path / "job"
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    job_dir.mkdir()
    input_dir.mkdir()
    input_file = input_dir / "sample.xlsx"
    input_file.write_bytes(b"placeholder")
    job_file = job_dir / "job.json"
    job_file.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "job-venv-001",
                "module_id": "moisture",
                "phase": "draft",
                "run_mode": "single",
                "input_files": [str(input_file)],
                "output_dir": str(output_dir),
            }
        ),
        encoding="utf-8",
    )
    run = run_cli("run", "--job", str(job_file), env=env)

    assert version.returncode == 0
    assert version.stdout == "0.1.0\n"
    assert version.stderr == ""
    assert self_check.returncode == 0
    assert self_check.stdout == ""
    assert "self-check: ok" in self_check.stderr
    assert run.returncode == 0
    assert run.stderr == ""
    assert (output_dir / "result.json").is_file()

import json
import subprocess
import sys
from pathlib import Path

from core.contracts.validator import validate_module


def write_module(module_dir: Path, entrypoint: str) -> None:
    module_dir.mkdir()
    manifest = {
        "schema_version": "1.0",
        "module_id": "moisture",
        "module_name": "原竹丝水分检测",
        "module_version": "0.1.0",
        "entrypoint": entrypoint,
        "supported_extensions": [".xlsx"],
        "supports_single_file": True,
        "supports_batch": True,
        "supports_incremental": True,
        "requires_network": False,
    }
    (module_dir / "module.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name in ["README.md", "CHANGELOG.md", "requirements.txt"]:
        (module_dir / name).write_text("ok\n", encoding="utf-8")
    for name in ["src", "tests", "samples", "docs"]:
        (module_dir / name).mkdir()


def test_validator_reports_missing_required_files(tmp_path: Path) -> None:
    report = validate_module(tmp_path)
    assert report.ok is False
    assert {issue.code for issue in report.issues} >= {
        "missing-module-json",
        "missing-entrypoint",
    }


def test_validator_accepts_minimal_module(tmp_path: Path) -> None:
    module_dir = tmp_path / "module"
    write_module(module_dir, "run_module.bat")
    (module_dir / "run_module.bat").write_text("@echo off\nexit /b 0\n", encoding="utf-8")

    assert validate_module(module_dir).ok is True


def test_validator_accepts_complete_monthly_rollup_contract(tmp_path: Path) -> None:
    module_dir = tmp_path / "module"
    write_module(module_dir, "run_module.bat")
    (module_dir / "run_module.bat").write_text("@exit /b 0\n", encoding="utf-8")
    schema_dir = module_dir / "schemas"
    schema_dir.mkdir()
    for name in ("snapshot.json", "request.json", "response.json"):
        (schema_dir / name).write_text(
            json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}),
            encoding="utf-8",
        )
    manifest_path = module_dir / "module.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capabilities"] = ["monthly_rollup"]
    manifest["monthly_rollup"] = {
        "schema_version": "1.0",
        "entrypoint": "run_module.bat",
        "snapshot_schema": "schemas/snapshot.json",
        "request_schema": "schemas/request.json",
        "response_schema": "schemas/response.json",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert validate_module(module_dir).ok is True


def test_validator_rejects_absolute_entrypoint(tmp_path: Path) -> None:
    outside_entrypoint = tmp_path / "outside.cmd"
    outside_entrypoint.write_text("@exit /b 0\n", encoding="utf-8")
    module_dir = tmp_path / "module"
    write_module(module_dir, str(outside_entrypoint.resolve()))

    report = validate_module(module_dir)

    assert report.ok is False
    assert "invalid-entrypoint" in {issue.code for issue in report.issues}


def test_validator_rejects_entrypoint_traversal_outside_module(tmp_path: Path) -> None:
    outside_entrypoint = tmp_path / "outside.cmd"
    outside_entrypoint.write_text("@exit /b 0\n", encoding="utf-8")
    module_dir = tmp_path / "module"
    write_module(module_dir, "../outside.cmd")

    report = validate_module(module_dir)

    assert report.ok is False
    assert "invalid-entrypoint" in {issue.code for issue in report.issues}


def test_validator_rejects_directory_entrypoint(tmp_path: Path) -> None:
    module_dir = tmp_path / "module"
    write_module(module_dir, "launcher.cmd")
    (module_dir / "launcher.cmd").mkdir()

    report = validate_module(module_dir)

    assert report.ok is False
    assert "invalid-entrypoint" in {issue.code for issue in report.issues}


def test_validator_rejects_unsupported_entrypoint_extension(tmp_path: Path) -> None:
    module_dir = tmp_path / "module"
    write_module(module_dir, "run_module.exe")
    (module_dir / "run_module.exe").write_bytes(b"not an executable")

    report = validate_module(module_dir)

    assert report.ok is False
    assert "invalid-entrypoint" in {issue.code for issue in report.issues}


def run_validator_cli(module_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "app.tools.module_contract_cli",
            "validate",
            str(module_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validator_cli_returns_one_for_invalid_entrypoint(tmp_path: Path) -> None:
    module_dir = tmp_path / "module"
    write_module(module_dir, "run_module.exe")
    (module_dir / "run_module.exe").write_bytes(b"not an executable")

    completed = run_validator_cli(module_dir)

    assert completed.returncode == 1
    assert completed.stdout.startswith("invalid-entrypoint:")
    assert completed.stderr == ""


def test_validator_cli_returns_zero_for_valid_launcher(tmp_path: Path) -> None:
    module_dir = tmp_path / "module"
    write_module(module_dir, "run_module.cmd")
    (module_dir / "run_module.cmd").write_text("@exit /b 0\n", encoding="utf-8")

    completed = run_validator_cli(module_dir)

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""

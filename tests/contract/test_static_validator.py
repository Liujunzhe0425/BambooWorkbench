import json
from pathlib import Path

from core.contracts.validator import validate_module


def test_validator_reports_missing_required_files(tmp_path: Path) -> None:
    report = validate_module(tmp_path)
    assert report.ok is False
    assert {issue.code for issue in report.issues} >= {
        "missing-module-json",
        "missing-entrypoint",
    }


def test_validator_accepts_minimal_module(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "1.0",
        "module_id": "moisture",
        "module_name": "原竹丝水分检测",
        "module_version": "0.1.0",
        "entrypoint": "run_module.bat",
        "supported_extensions": [".xlsx"],
        "supports_single_file": True,
        "supports_batch": True,
        "supports_incremental": True,
        "requires_network": False,
    }
    (tmp_path / "module.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "run_module.bat").write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    for name in ["README.md", "CHANGELOG.md", "requirements.txt"]:
        (tmp_path / name).write_text("ok\n", encoding="utf-8")
    for name in ["src", "tests", "samples", "docs"]:
        (tmp_path / name).mkdir()
    assert validate_module(tmp_path).ok is True

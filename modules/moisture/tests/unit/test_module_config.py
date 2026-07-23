from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.module_config import (
    ModuleConfigError,
    ModuleOperation,
    load_module_config,
)


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_and_legacy_config_default_to_summary(tmp_path: Path) -> None:
    missing = load_module_config(None, input_count=1)
    legacy = load_module_config(
        _write(tmp_path / "legacy.json", {"default_year": 2026}), input_count=1
    )

    assert missing.operation is ModuleOperation.SUMMARY
    assert missing.default_year is None
    assert legacy.operation is ModuleOperation.SUMMARY
    assert legacy.default_year == 2026


def test_versioned_summary_is_strict(tmp_path: Path) -> None:
    parsed = load_module_config(
        _write(
            tmp_path / "summary.json",
            {"schema_version": "1.0", "operation": "summary", "default_year": 2026},
        ),
        input_count=1,
    )
    assert parsed.operation is ModuleOperation.SUMMARY
    assert parsed.default_year == 2026


def test_ai_report_config_keeps_only_roles_and_stable_selections(tmp_path: Path) -> None:
    parsed = load_module_config(
        _write(
            tmp_path / "ai-report.json",
            {
                "schema_version": "1.0",
                "operation": "ai_report",
                "inputs": [{"role": "current_summary", "input_index": 0}],
                "history_ids": ["history-001"],
                "experience_selections": [
                    {"entry_id": "EXP-001", "version": "1.0.0", "sha256": "a" * 64}
                ],
                "question": "Summarize the current period.",
            },
        ),
        input_count=1,
    )

    assert parsed.operation is ModuleOperation.AI_REPORT
    assert parsed.current_summary_input_index == 0
    assert parsed.history_ids == ("history-001",)
    assert parsed.experience_selections[0].entry_id == "EXP-001"


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": "1.0", "operation": "unknown"},
        {"schema_version": "1.0", "operation": "summary", "provider": "deepseek"},
        {
            "schema_version": "1.0",
            "operation": "ai_report",
            "inputs": [{"role": "current_summary", "input_index": 1}],
            "history_ids": [],
            "experience_selections": [],
            "question": "question",
        },
        {
            "schema_version": "1.0",
            "operation": "ai_report",
            "inputs": [{"role": "current_summary", "input_index": 0}],
            "history_ids": ["../escape"],
            "experience_selections": [],
            "question": "question",
        },
        {
            "schema_version": "1.0",
            "operation": "ai_report",
            "inputs": [{"role": "current_summary", "input_index": 0}],
            "history_ids": [],
            "experience_selections": [],
            "question": "question",
            "api_key": "secret",
        },
    ),
)
def test_invalid_operation_paths_and_secret_fields_are_rejected(
    tmp_path: Path, payload: object
) -> None:
    with pytest.raises(ModuleConfigError):
        load_module_config(_write(tmp_path / "invalid.json", payload), input_count=1)

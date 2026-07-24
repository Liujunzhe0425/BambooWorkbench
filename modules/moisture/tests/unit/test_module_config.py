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


def test_summary_config_accepts_a_pinned_rule_snapshot(tmp_path: Path) -> None:
    parsed = load_module_config(
        _write(
            tmp_path / "summary-rules.json",
            {
                "schema_version": "1.0",
                "operation": "summary",
                "rule_selection": {
                    "version": "default-v2-approved",
                    "sha256": "a" * 64,
                },
            },
        ),
        input_count=1,
    )

    assert parsed.rule_selection is not None
    assert parsed.rule_selection.version == "default-v2-approved"
    assert parsed.rule_selection.sha256 == "a" * 64


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"version": "v1"},
        {"version": "../v1", "sha256": "a" * 64},
        {"version": "v1", "sha256": "not-a-hash"},
    ],
)
def test_rule_selection_rejects_incomplete_or_unsafe_identity(
    tmp_path: Path, selection: object
) -> None:
    with pytest.raises(ModuleConfigError, match="rule_selection"):
        load_module_config(
            _write(
                tmp_path / "invalid-rule-selection.json",
                {
                    "schema_version": "1.0",
                    "operation": "summary",
                    "rule_selection": selection,
                },
            ),
            input_count=1,
        )


def test_append_summary_config_assigns_one_base_and_all_new_inputs(tmp_path: Path) -> None:
    parsed = load_module_config(
        _write(
            tmp_path / "append-summary.json",
            {
                "schema_version": "1.0",
                "operation": "append_summary",
                "inputs": [
                    {"role": "new_raw", "input_index": 2},
                    {"role": "base_summary", "input_index": 0},
                    {"role": "new_raw", "input_index": 1},
                ],
                "default_year": 2026,
            },
        ),
        input_count=3,
    )

    assert parsed.operation is ModuleOperation.APPEND_SUMMARY
    assert parsed.base_summary_input_index == 0
    assert parsed.new_raw_input_indexes == (2, 1)
    assert parsed.default_year == 2026
    assert parsed.current_summary_input_index is None
    assert parsed.history_ids == ()


@pytest.mark.parametrize(
    ("inputs", "input_count"),
    (
        ([{"role": "base_summary", "input_index": 0}], 1),
        (
            [
                {"role": "base_summary", "input_index": 0},
                {"role": "base_summary", "input_index": 1},
            ],
            2,
        ),
        (
            [
                {"role": "base_summary", "input_index": 0},
                {"role": "new_raw", "input_index": 0},
            ],
            2,
        ),
        (
            [
                {"role": "base_summary", "input_index": 0},
                {"role": "new_raw", "input_index": 2},
            ],
            2,
        ),
        (
            [
                {"role": "base_summary", "input_index": 0},
                {"role": "new_raw", "input_index": 1},
            ],
            3,
        ),
        (
            [
                {"role": "base_summary", "input_index": 0},
                {"role": "historical_raw", "input_index": 1},
            ],
            2,
        ),
    ),
)
def test_append_summary_rejects_ambiguous_or_unassigned_input_roles(
    tmp_path: Path,
    inputs: list[dict[str, object]],
    input_count: int,
) -> None:
    with pytest.raises(ModuleConfigError, match="append_summary"):
        load_module_config(
            _write(
                tmp_path / "invalid-append.json",
                {
                    "schema_version": "1.0",
                    "operation": "append_summary",
                    "inputs": inputs,
                },
            ),
            input_count=input_count,
        )


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

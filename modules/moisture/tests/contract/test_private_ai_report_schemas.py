from __future__ import annotations

# ruff: noqa: E402, I001

import copy
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.contract.private_schemas import (
    PRIVATE_SCHEMA_NAMES,
    PrivateSchemaError,
    load_private_schema,
    validate_private_payload,
)

HASH = "a" * 64


def _response_schema() -> dict[str, object]:
    return load_private_schema("ai-analysis-response.schema.json", MODULE_ROOT)


def _request() -> dict[str, object]:
    return {
        "request_id": "msr-ai-report-" + "b" * 24,
        "service": "ai",
        "scope": None,
        "purpose": "moisture_summary_analysis",
        "requires_user_consent": True,
        "response_format": "json_object",
        "payload": {
            "schema_version": "1.0",
            "context_hash": HASH,
            "question": "Compare the current period with history.",
            "current_summary": {
                "content_hash": HASH,
                "batch_count": 21,
                "date_range": {"start": "2026-04-01", "end": "2026-04-30"},
                "metrics": {"mean": "0.50"},
                "review_items": [],
            },
            "history_summaries": [],
            "experiences": [],
            "rule_snapshot": {"version": "rules-v1", "sha256": HASH, "summary": "Rules"},
            "selection_counts": {
                "history": {"total": 0, "sent": 0, "omitted": 0},
                "experiences": {"total": 0, "sent": 0, "omitted": 0},
                "review_items": {"total": 0, "sent": 0, "omitted": 0},
            },
            "instruction": "Return only JSON matching response_schema.",
            "response_schema": _response_schema(),
        },
    }


def test_all_private_schemas_are_valid_draft_2020_12() -> None:
    for name in PRIVATE_SCHEMA_NAMES:
        assert load_private_schema(name, MODULE_ROOT)["$schema"].endswith("2020-12/schema")


def test_ai_analysis_request_is_consent_gated_and_path_free() -> None:
    request = _request()
    validate_private_payload("ai-analysis-request.schema.json", request, MODULE_ROOT)
    serialized = str(request).lower()
    assert request["requires_user_consent"] is True
    assert "c:\\" not in serialized
    assert "api_key" not in serialized
    assert "provider" not in serialized


@pytest.mark.parametrize("field", ("api_key", "provider", "absolute_path"))
def test_ai_analysis_request_rejects_host_secrets_and_paths(field: str) -> None:
    request = _request()
    request[field] = "forbidden"
    with pytest.raises(PrivateSchemaError):
        validate_private_payload("ai-analysis-request.schema.json", request, MODULE_ROOT)


def test_success_and_degraded_result_contracts_are_distinct() -> None:
    success = {
        "schema_version": "1.0",
        "status": "success",
        "request_id": "msr-ai-report-" + "b" * 24,
        "context_hash": HASH,
        "current_summary": {"display_name": "April summary", "sha256": HASH},
        "history_ids": [],
        "experience_selections": [],
        "report_file": "ai_analysis_report.md",
        "degradation_reason": None,
    }
    degraded = copy.deepcopy(success)
    degraded.update(status="denied", report_file=None, degradation_reason="user_denied_network")
    validate_private_payload("ai-analysis-result.schema.json", success, MODULE_ROOT)
    validate_private_payload("ai-analysis-result.schema.json", degraded, MODULE_ROOT)

    invalid = copy.deepcopy(degraded)
    invalid["report_file"] = "ai_analysis_report.md"
    with pytest.raises(PrivateSchemaError):
        validate_private_payload("ai-analysis-result.schema.json", invalid, MODULE_ROOT)


def test_history_index_rejects_path_escape_and_unknown_format() -> None:
    entry = {
        "history_id": "history-001",
        "display_name": "April summary",
        "storage_name": "history-001.xlsx",
        "sha256": HASH,
        "format_version": "1.0.1-four-sheet",
        "date_start": "2026-04-01",
        "date_end": "2026-04-30",
        "batch_count": 21,
        "status": "active",
    }
    validate_private_payload(
        "history-index.schema.json", {"schema_version": "1.0", "entries": [entry]}, MODULE_ROOT
    )

    escaped = copy.deepcopy(entry)
    escaped["storage_name"] = "../escape.xlsx"
    with pytest.raises(PrivateSchemaError):
        validate_private_payload(
            "history-index.schema.json",
            {"schema_version": "1.0", "entries": [escaped]},
            MODULE_ROOT,
        )

# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.service_response_validator import (
    AIResponseValidationError,
    validate_ai_response_text,
)


def _request() -> dict[str, object]:
    return {
        "request_id": "msr-ai-request",
        "service": "ai",
        "payload": {
            "schema_version": "1.0",
            "rule_hash": "a" * 64,
            "candidates": [
                {
                    "candidate_id": "candidate-0123456789abcdef",
                    "direction": "high",
                    "field": "mean",
                    "observed_value": "0.60",
                    "threshold": "0.55",
                    "relative_deviation": "0.09",
                    "evidence_refs": ["rule:RULE-HIGH", "experience:EXP-1@1.0.0"],
                }
            ],
        },
    }


def _response() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "rule_hash": "a" * 64,
        "decisions": [
            {
                "candidate_id": "candidate-0123456789abcdef",
                "direction": "high",
                "field": "mean",
                "observed_value": "0.600",
                "decision": "escalate",
                "confidence": 0.80,
                "reason": "structured review",
                "evidence_refs": ["rule:RULE-HIGH"],
            }
        ],
    }


def test_valid_response_matches_candidate_rule_and_evidence_at_threshold() -> None:
    decisions = validate_ai_response_text(json.dumps(_response()), _request())

    assert len(decisions) == 1
    assert str(decisions[0].confidence) == "0.8"
    assert decisions[0].direction == "high"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rule_hash", "b" * 64),
        ("direction", "low"),
        ("field", "maximum"),
        ("observed_value", "0.61"),
        ("confidence", 0.79),
        ("evidence_refs", ["experience:UNKNOWN@1.0.0"]),
        ("candidate_id", "candidate-ffffffffffffffff"),
    ],
)
def test_mismatched_or_low_confidence_evidence_is_rejected(field: str, value: object) -> None:
    response = deepcopy(_response())
    if field == "rule_hash":
        response[field] = value
    else:
        response["decisions"][0][field] = value  # type: ignore[index]

    with pytest.raises(AIResponseValidationError):
        validate_ai_response_text(json.dumps(response), _request())


def test_non_json_and_duplicate_candidate_decisions_are_rejected() -> None:
    with pytest.raises(AIResponseValidationError):
        validate_ai_response_text("mock provider plain text", _request())
    response = _response()
    response["decisions"] = [response["decisions"][0], response["decisions"][0]]  # type: ignore[index]
    with pytest.raises(AIResponseValidationError):
        validate_ai_response_text(json.dumps(response), _request())

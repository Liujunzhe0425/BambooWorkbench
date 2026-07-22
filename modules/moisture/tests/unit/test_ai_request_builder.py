from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from decimal import Decimal
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.ai_request_builder import MAX_PAYLOAD_BYTES, build_ai_request
from moisture.domain.review import AIReviewCandidate


def candidate(identity: str, deviation: str, field: str = "total_average") -> AIReviewCandidate:
    return AIReviewCandidate(identity, field, Decimal("0.61"), Decimal("0.55"), Decimal(deviation))


def test_request_is_stable_sorted_redacted_and_declares_consent() -> None:
    secret = "客户甲-C:/secret/supplier.xlsx"
    values = (candidate("b", "0.10"), candidate(secret, "0.20", secret), candidate("a", "0.10"))

    first = build_ai_request(root_job_id="draft-root", candidates=values, rule_hash="a" * 64)
    second = build_ai_request(
        root_job_id="draft-root", candidates=tuple(reversed(values)), rule_hash="a" * 64
    )

    assert first.request is not None and second.request is not None
    assert first.request["request_id"] == second.request["request_id"]
    assert first.request["payload"] == second.request["payload"]
    assert first.request["requires_user_consent"] is True
    assert first.request["response_format"] == "json_object"
    assert first.request["payload"]["response_schema"]["type"] == "object"
    assert "仅返回" in first.request["payload"]["instruction"]
    serialized = json.dumps(first.request, ensure_ascii=False)
    assert secret not in serialized and "C:/secret" not in serialized and "客户甲" not in serialized


def test_candidate_limit_and_utf8_payload_budget_keep_omission_counts() -> None:
    values = tuple(candidate(f"candidate-{index}", str(index / 100)) for index in range(75))

    built = build_ai_request(root_job_id="draft-root", candidates=values, rule_hash="b" * 64)

    assert built.request is not None
    assert (built.candidate_total, built.candidate_sent, built.candidate_omitted) == (75, 50, 25)
    payload = built.request["payload"]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    assert len(encoded) <= MAX_PAYLOAD_BYTES


def test_request_identity_is_stable_when_governed_evidence_is_added_after_confirmation() -> None:
    draft_candidate = candidate("same-business-candidate", "0.10")
    finalized_candidate = AIReviewCandidate(
        candidate_id=draft_candidate.candidate_id,
        target_field=draft_candidate.target_field,
        observed_value=draft_candidate.observed_value,
        reference_value=draft_candidate.reference_value,
        relative_deviation=draft_candidate.relative_deviation,
        evidence_refs=("rule:HIGH_DEFAULT", "experience:EXP-GENERIC-001@1.0.0"),
    )

    draft = build_ai_request(
        root_job_id="draft-root",
        candidates=(draft_candidate,),
        rule_hash="c" * 64,
    )
    finalized = build_ai_request(
        root_job_id="draft-root",
        candidates=(finalized_candidate,),
        rule_hash="c" * 64,
    )

    assert draft.request is not None and finalized.request is not None
    assert draft.request["payload"] != finalized.request["payload"]
    assert draft.request["request_id"] == finalized.request["request_id"]

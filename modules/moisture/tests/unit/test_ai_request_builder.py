from __future__ import annotations

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
    second = build_ai_request(root_job_id="draft-root", candidates=tuple(reversed(values)), rule_hash="a" * 64)

    assert first.request is not None and second.request is not None
    assert first.request["request_id"] == second.request["request_id"]
    assert first.request["payload"] == second.request["payload"]
    assert first.request["requires_user_consent"] is True
    serialized = json.dumps(first.request, ensure_ascii=False)
    assert secret not in serialized and "C:/secret" not in serialized and "客户甲" not in serialized


def test_candidate_limit_and_utf8_payload_budget_keep_omission_counts() -> None:
    values = tuple(candidate(f"candidate-{index}", str(index / 100)) for index in range(75))

    built = build_ai_request(root_job_id="draft-root", candidates=values, rule_hash="b" * 64)

    assert built.request is not None
    assert (built.candidate_total, built.candidate_sent, built.candidate_omitted) == (75, 50, 25)
    payload = built.request["payload"]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= MAX_PAYLOAD_BYTES

"""Build a deterministic, bounded AI review request without calling AI."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from moisture.domain.review import AIReviewCandidate

MAX_CANDIDATES = 50
MAX_PAYLOAD_BYTES = 65_536


@dataclass(frozen=True, slots=True)
class AIRequestBuildResult:
    request: dict[str, object] | None
    candidate_total: int
    candidate_sent: int
    candidate_omitted: int


def _safe_field(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_\-]", "_", value)[:64]
    return normalized or "moisture_metric"


def _candidate_summary(candidate: AIReviewCandidate) -> dict[str, object]:
    opaque_id = hashlib.sha256(candidate.candidate_id.encode("utf-8")).hexdigest()[:16]
    return {
        "candidate_id": f"candidate-{opaque_id}",
        "target_field": _safe_field(candidate.target_field),
        "observed_value": str(candidate.observed_value),
        "reference_value": str(candidate.reference_value),
        "relative_deviation": str(candidate.relative_deviation),
    }


def _payload_size(payload: dict[str, object]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def build_ai_request(
    *,
    root_job_id: str,
    candidates: tuple[AIReviewCandidate, ...],
    rule_hash: str,
) -> AIRequestBuildResult:
    """Summarize, redact, sort and budget optional review candidates."""

    ordered = sorted(candidates, key=lambda item: (-item.relative_deviation, item.candidate_id))
    total = len(ordered)
    if not ordered:
        return AIRequestBuildResult(None, 0, 0, 0)

    summaries: list[dict[str, object]] = []
    for candidate in ordered[:MAX_CANDIDATES]:
        proposed = [*summaries, _candidate_summary(candidate)]
        payload = {
            "instruction": "仅基于规范化候选摘要提供竹丝水分复核建议",
            "candidates": proposed,
            "candidate_total": total,
            "candidate_sent": len(proposed),
            "candidate_omitted": total - len(proposed),
        }
        if _payload_size(payload) > MAX_PAYLOAD_BYTES:
            break
        summaries = proposed

    sent = len(summaries)
    omitted = total - sent
    payload = {
        "instruction": "仅基于规范化候选摘要提供竹丝水分复核建议",
        "candidates": summaries,
        "candidate_total": total,
        "candidate_sent": sent,
        "candidate_omitted": omitted,
    }
    candidate_digest = hashlib.sha256(
        json.dumps(summaries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    identity = hashlib.sha256(
        json.dumps(
            {
                "root_job_id": root_job_id,
                "module": "moisture",
                "service": "ai",
                "rule_hash": rule_hash,
                "candidate_digest": candidate_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    request = {
        "request_id": f"msr-ai-{identity}",
        "service": "ai",
        "scope": None,
        "purpose": "复核水分规则候选摘要",
        "payload": payload,
        "requires_user_consent": True,
    }
    return AIRequestBuildResult(request, total, sent, omitted)

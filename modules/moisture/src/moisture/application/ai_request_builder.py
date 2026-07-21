"""Build a deterministic, bounded AI review request without calling AI."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from moisture.domain.enums import DisplayColor
from moisture.domain.review import AIReviewCandidate
from moisture.domain.rules import RulePackageSnapshot
from moisture.ports.writers import WorkbookBatch

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


def opaque_candidate_id(candidate: AIReviewCandidate) -> str:
    """Return the public, identity-free candidate ID used in the request."""

    opaque_id = hashlib.sha256(candidate.candidate_id.encode("utf-8")).hexdigest()[:16]
    return f"candidate-{opaque_id}"


def _candidate_summary(candidate: AIReviewCandidate) -> dict[str, object]:
    direction = candidate.direction or (
        "high" if candidate.observed_value > candidate.reference_value else "low"
    )
    return {
        "candidate_id": opaque_candidate_id(candidate),
        "direction": direction,
        "field": _safe_field(candidate.target_field),
        "observed_value": str(candidate.observed_value),
        "threshold": str(candidate.reference_value),
        "relative_deviation": str(candidate.relative_deviation),
        "evidence_refs": list(candidate.evidence_refs),
    }


def ordered_candidates(
    candidates: tuple[AIReviewCandidate, ...],
) -> tuple[AIReviewCandidate, ...]:
    return tuple(sorted(candidates, key=lambda item: (-item.relative_deviation, item.candidate_id)))


def candidates_from_batches(
    batches: tuple[WorkbookBatch, ...], snapshot: RulePackageSnapshot
) -> tuple[AIReviewCandidate, ...]:
    """Extract privacy-minimal candidates from confirmed deterministic rule hits."""

    definitions = {item.rule_id: item for item in snapshot.definitions}
    candidates: list[AIReviewCandidate] = []
    for batch in batches:
        decisions = batch.screening_decisions or (batch.screening_decision,)
        for decision in decisions:
            if decision.display_color not in {DisplayColor.ORANGE, DisplayColor.GREEN}:
                continue
            target = decision.target_field
            if target is None:
                continue
            observed = getattr(batch.statistics, target, None)
            if target == "total_weight_kg":
                observed = batch.record.total_weight_kg
            if not hasattr(observed, "as_tuple"):
                continue
            hit = next((item for item in decision.rule_hits if item.target_field == target), None)
            definition = definitions.get(hit.rule_id) if hit is not None else None
            if hit is None or definition is None:
                continue
            threshold = definition.threshold
            if threshold is None:
                threshold = (
                    definition.upper
                    if decision.display_color is DisplayColor.ORANGE
                    else definition.lower
                )
            if threshold is None:
                continue
            relative = abs(observed - threshold) / abs(threshold) if threshold else abs(observed)
            fingerprint = batch.record.source_file_hash or batch.record.record_id
            raw_identity = f"{fingerprint}:{hit.rule_id}:{target}:{snapshot.rules_sha256}"
            evidence_refs = (f"rule:{hit.rule_id}",) + tuple(
                f"experience:{item.entry_id}@{item.version}"
                for item in batch.experience_references
            )
            candidates.append(
                AIReviewCandidate(
                    candidate_id=raw_identity,
                    target_field=target,
                    observed_value=observed,
                    reference_value=threshold,
                    relative_deviation=relative,
                    direction=(
                        "high" if decision.display_color is DisplayColor.ORANGE else "low"
                    ),
                    rule_id=hit.rule_id,
                    evidence_refs=evidence_refs,
                    record_id=batch.record.record_id,
                )
            )
    return ordered_candidates(tuple(candidates))


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

    ordered = ordered_candidates(candidates)
    total = len(ordered)
    if not ordered:
        return AIRequestBuildResult(None, 0, 0, 0)

    summaries: list[dict[str, object]] = []
    for candidate in ordered[:MAX_CANDIDATES]:
        proposed = [*summaries, _candidate_summary(candidate)]
        payload = {
            "schema_version": "1.0",
            "rule_hash": rule_hash,
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
        "schema_version": "1.0",
        "rule_hash": rule_hash,
        "instruction": "仅基于规范化候选摘要提供竹丝水分复核建议",
        "candidates": summaries,
        "candidate_total": total,
        "candidate_sent": sent,
        "candidate_omitted": omitted,
    }
    identity = hashlib.sha256(
        json.dumps(
            {
                "root_job_id": root_job_id,
                "module": "moisture",
                "service": "ai",
                "rule_hash": rule_hash,
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

"""Strict business validation for structured AI service response text."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from jsonschema import Draft202012Validator
from moisture.runtime_paths import module_root


class AIResponseValidationError(ValueError):
    """Provider text cannot be safely bound to the rebuilt request."""


@dataclass(frozen=True, slots=True)
class ValidatedReviewDecision:
    candidate_id: str
    direction: str
    field: str
    observed_value: Decimal
    confidence: Decimal
    evidence_refs: tuple[str, ...]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AIResponseValidationError("duplicate response field")
        result[key] = value
    return result


def _validator() -> Draft202012Validator:
    path = module_root() / "schemas" / "ai-review-response.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_ai_response_text(
    text: str | None, expected_request: Mapping[str, object]
) -> tuple[ValidatedReviewDecision, ...]:
    """Validate JSON schema and every request/candidate/evidence binding."""

    if not isinstance(text, str) or not text.strip():
        raise AIResponseValidationError("AI response text is missing")
    try:
        payload = json.loads(
            text,
            parse_float=Decimal,
            parse_int=Decimal,
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, UnicodeError, AIResponseValidationError) as error:
        raise AIResponseValidationError("AI response text is invalid JSON") from error
    if not isinstance(payload, Mapping):
        raise AIResponseValidationError("AI response must be an object")
    errors = sorted(_validator().iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        raise AIResponseValidationError("AI response schema is invalid")

    request_payload = expected_request.get("payload")
    if not isinstance(request_payload, Mapping):
        raise AIResponseValidationError("rebuilt AI request is invalid")
    if payload["rule_hash"] != request_payload.get("rule_hash"):
        raise AIResponseValidationError("AI response rule hash does not match")
    raw_candidates = request_payload.get("candidates")
    if not isinstance(raw_candidates, (list, tuple)):
        raise AIResponseValidationError("rebuilt AI candidates are invalid")
    candidates = {
        item.get("candidate_id"): item
        for item in raw_candidates
        if isinstance(item, Mapping) and isinstance(item.get("candidate_id"), str)
    }
    if len(candidates) != len(raw_candidates):
        raise AIResponseValidationError("rebuilt AI candidate IDs are not unique")

    decisions: list[ValidatedReviewDecision] = []
    seen: set[str] = set()
    for raw in payload["decisions"]:
        candidate_id = raw["candidate_id"]
        if candidate_id in seen:
            raise AIResponseValidationError("AI response candidate ID is duplicated")
        seen.add(candidate_id)
        expected = candidates.get(candidate_id)
        if expected is None:
            raise AIResponseValidationError("AI response candidate ID is unknown")
        if raw["direction"] != expected.get("direction"):
            raise AIResponseValidationError("AI response direction does not match")
        if raw["field"] != expected.get("field"):
            raise AIResponseValidationError("AI response field does not match")
        try:
            observed = Decimal(raw["observed_value"])
            expected_observed = Decimal(str(expected.get("observed_value")))
        except (InvalidOperation, TypeError) as error:
            raise AIResponseValidationError("AI observed value is invalid") from error
        if observed != expected_observed:
            raise AIResponseValidationError("AI observed value does not match")
        confidence = Decimal(str(raw["confidence"]))
        if confidence < Decimal("0.80"):
            raise AIResponseValidationError("AI confidence is below the formal threshold")
        allowed_evidence = expected.get("evidence_refs")
        if not isinstance(allowed_evidence, (list, tuple)) or not set(
            raw["evidence_refs"]
        ).issubset(set(allowed_evidence)):
            raise AIResponseValidationError("AI response cites unknown evidence")
        decisions.append(
            ValidatedReviewDecision(
                candidate_id=candidate_id,
                direction=raw["direction"],
                field=raw["field"],
                observed_value=observed,
                confidence=confidence,
                evidence_refs=tuple(raw["evidence_refs"]),
            )
        )
    if seen != set(candidates):
        raise AIResponseValidationError("AI response does not cover every candidate")
    return tuple(decisions)

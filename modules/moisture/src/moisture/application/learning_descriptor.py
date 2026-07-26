"""Build privacy-minimal, stable learning descriptors for mapping confirmations."""

from __future__ import annotations

import hashlib
import json
import unicodedata

from moisture.contract.learning_descriptor import (
    LearningCandidate,
    LearningContextLevel,
    LearningDescriptor,
    LearningDescriptorError,
)
from moisture.domain.models import BusinessConfirmationIssue

_LEARNABLE_FIELDS = {
    "supplier_mapping": "supplier",
    "department_mapping": "department",
}
_DEFAULT_SOURCE_CATEGORIES = {
    "supplier_mapping": "workbook_header",
    "department_mapping": "workbook_sample_rows",
}
_ALLOWED_SOURCE_CATEGORIES = {
    "workbook_header",
    "workbook_sample_rows",
    "unspecified",
}


def _stable_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:24]


def _material_category(material_type: str | None) -> str:
    if material_type is None:
        return "unspecified"
    normalized = unicodedata.normalize("NFKC", material_type).strip().casefold()
    if normalized in {"竹丝", "原竹丝", "raw_bamboo_filament"}:
        return "raw_bamboo_filament"
    return "unspecified"


def _candidate_identity_value(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _learning_key(
    *,
    module_id: str,
    field: str,
    material_category: str | None,
    source_category: str | None,
) -> str:
    context: dict[str, object] = {
        "module_id": module_id,
        "field": field,
    }
    if material_category is not None:
        context["material_category"] = material_category
    if source_category is not None:
        context["source_category"] = source_category
    return f"msr-learning-{_stable_digest(context)}"


def _context_level(
    *,
    module_id: str,
    field: str,
    material_category: str | None,
    source_category: str | None,
) -> LearningContextLevel:
    return LearningContextLevel(
        learning_key=_learning_key(
            module_id=module_id,
            field=field,
            material_category=material_category,
            source_category=source_category,
        ),
        module_id=module_id,
        field=field,
        material_category=material_category,
        source_category=source_category,
    )


def _candidates(
    *,
    module_id: str,
    field: str,
    values: tuple[str, ...],
) -> tuple[LearningCandidate, ...]:
    display_values = tuple(sorted({value.strip() for value in values if value.strip()}))
    candidates = tuple(
        LearningCandidate(
            candidate_id=(
                "msr-candidate-"
                + _stable_digest(
                    {
                        "module_id": module_id,
                        "field": field,
                        "value": _candidate_identity_value(display_text),
                    }
                )
            ),
            display_text=display_text,
        )
        for display_text in display_values
    )
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise LearningDescriptorError(
            "LEARNING_DESCRIPTOR_CANDIDATE_CONFLICT",
            "learning candidates are not uniquely identifiable",
        )
    return candidates


def build_learning_descriptor(
    issue: BusinessConfirmationIssue,
    *,
    module_id: str = "moisture",
    material_type: str | None = None,
    source_category: str | None = None,
) -> LearningDescriptor | None:
    """Build one private descriptor, or return ``None`` for non-learnable issues."""

    field = _LEARNABLE_FIELDS.get(issue.kind)
    if field is None:
        return None
    if issue.field != field:
        raise LearningDescriptorError(
            "LEARNING_DESCRIPTOR_FIELD_MISMATCH",
            "learning confirmation field does not match its mapping type",
        )
    selected_source = (
        _DEFAULT_SOURCE_CATEGORIES[issue.kind]
        if source_category is None
        else source_category
    )
    if selected_source not in _ALLOWED_SOURCE_CATEGORIES:
        raise LearningDescriptorError(
            "LEARNING_DESCRIPTOR_CONTEXT_INVALID",
            "learning source category is invalid",
        )
    material_category = _material_category(material_type)
    context_levels = (
        _context_level(
            module_id=module_id,
            field=field,
            material_category=material_category,
            source_category=selected_source,
        ),
        _context_level(
            module_id=module_id,
            field=field,
            material_category=material_category,
            source_category=None,
        ),
        _context_level(
            module_id=module_id,
            field=field,
            material_category=None,
            source_category=None,
        ),
    )
    candidates = _candidates(
        module_id=module_id,
        field=field,
        values=issue.candidates,
    )
    suggestion = issue.suggested_value.strip() if issue.suggested_value else None
    suggestion_by_display = {
        candidate.display_text: candidate.candidate_id for candidate in candidates
    }
    return LearningDescriptor(
        learning_key=context_levels[0].learning_key,
        field=field,
        context=context_levels[0],
        context_levels=context_levels,
        candidates=candidates,
        base_suggestion=suggestion_by_display.get(suggestion),
        preference_adjustable=True,
    )

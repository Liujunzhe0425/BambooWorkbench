"""Private immutable learning descriptor contract for remembered confirmations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_KEY = re.compile(r"^msr-learning-[0-9a-f]{24}$")
_CANDIDATE_ID = re.compile(r"^msr-candidate-[0-9a-f]{24}$")
_FIELDS = {"supplier", "department"}
_MATERIAL_CATEGORIES = {"raw_bamboo_filament", "unspecified"}
_SOURCE_CATEGORIES = {
    "workbook_header",
    "workbook_sample_rows",
    "unspecified",
}


class LearningDescriptorError(ValueError):
    """Stable, sanitized error raised by the private learning contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LearningCandidate:
    candidate_id: str
    display_text: str

    def __post_init__(self) -> None:
        if (
            not _CANDIDATE_ID.fullmatch(self.candidate_id)
            or not self.display_text.strip()
            or len(self.display_text) > 300
            or any(ord(character) < 32 for character in self.display_text)
        ):
            raise LearningDescriptorError(
                "LEARNING_DESCRIPTOR_INVALID",
                "learning candidate is invalid",
            )

    def to_payload(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "display_text": self.display_text,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> LearningCandidate:
        try:
            return cls(
                candidate_id=str(payload["candidate_id"]),
                display_text=str(payload["display_text"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, LearningDescriptorError):
                raise
            raise LearningDescriptorError(
                "LEARNING_DESCRIPTOR_INVALID",
                "learning candidate is invalid",
            ) from error


@dataclass(frozen=True, slots=True)
class LearningContextLevel:
    learning_key: str
    module_id: str
    field: str
    material_category: str | None
    source_category: str | None

    def __post_init__(self) -> None:
        if (
            not _KEY.fullmatch(self.learning_key)
            or not _IDENTIFIER.fullmatch(self.module_id)
            or self.field not in _FIELDS
            or (
                self.material_category is not None
                and self.material_category not in _MATERIAL_CATEGORIES
            )
            or (
                self.source_category is not None
                and self.source_category not in _SOURCE_CATEGORIES
            )
        ):
            raise LearningDescriptorError(
                "LEARNING_DESCRIPTOR_INVALID",
                "learning context is invalid",
            )

    def context_payload(self) -> dict[str, str]:
        payload = {
            "module_id": self.module_id,
            "field": self.field,
        }
        if self.material_category is not None:
            payload["material_category"] = self.material_category
        if self.source_category is not None:
            payload["source_category"] = self.source_category
        return payload

    def to_payload(self) -> dict[str, object]:
        return {
            "learning_key": self.learning_key,
            "context": self.context_payload(),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> LearningContextLevel:
        try:
            context = payload["context"]
            if not isinstance(context, Mapping):
                raise TypeError
            material = context.get("material_category")
            source = context.get("source_category")
            return cls(
                learning_key=str(payload["learning_key"]),
                module_id=str(context["module_id"]),
                field=str(context["field"]),
                material_category=None if material is None else str(material),
                source_category=None if source is None else str(source),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, LearningDescriptorError):
                raise
            raise LearningDescriptorError(
                "LEARNING_DESCRIPTOR_INVALID",
                "learning context is invalid",
            ) from error


@dataclass(frozen=True, slots=True)
class LearningDescriptor:
    learning_key: str
    field: str
    context: LearningContextLevel
    context_levels: tuple[LearningContextLevel, ...]
    candidates: tuple[LearningCandidate, ...]
    base_suggestion: str | None
    preference_adjustable: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_levels", tuple(self.context_levels))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        display_values = [candidate.display_text for candidate in self.candidates]
        level_keys = [level.learning_key for level in self.context_levels]
        if (
            self.field not in _FIELDS
            or self.learning_key != self.context.learning_key
            or not self.context_levels
            or self.context_levels[0] != self.context
            or len(level_keys) != len(set(level_keys))
            or not self.candidates
            or len(candidate_ids) != len(set(candidate_ids))
            or len(display_values) != len(set(display_values))
            or (
                self.base_suggestion is not None
                and self.base_suggestion not in candidate_ids
            )
            or self.preference_adjustable is not True
        ):
            raise LearningDescriptorError(
                "LEARNING_DESCRIPTOR_INVALID",
                "learning descriptor is invalid",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "learning_key": self.learning_key,
            "field": self.field,
            "context": self.context.context_payload(),
            "context_levels": [level.to_payload() for level in self.context_levels],
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "base_suggestion": self.base_suggestion,
            "preference_adjustable": self.preference_adjustable,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> LearningDescriptor:
        try:
            context = payload["context"]
            levels = payload["context_levels"]
            candidates = payload["candidates"]
            if (
                not isinstance(context, Mapping)
                or not isinstance(levels, list)
                or not isinstance(candidates, list)
                or any(not isinstance(level, Mapping) for level in levels)
                or any(not isinstance(candidate, Mapping) for candidate in candidates)
                or not isinstance(payload["preference_adjustable"], bool)
            ):
                raise TypeError
            key = str(payload["learning_key"])
            primary_context = LearningContextLevel.from_payload(
                {"learning_key": key, "context": context}
            )
            suggestion = payload["base_suggestion"]
            return cls(
                learning_key=key,
                field=str(payload["field"]),
                context=primary_context,
                context_levels=tuple(
                    LearningContextLevel.from_payload(level) for level in levels
                ),
                candidates=tuple(
                    LearningCandidate.from_payload(candidate)
                    for candidate in candidates
                ),
                base_suggestion=None if suggestion is None else str(suggestion),
                preference_adjustable=payload["preference_adjustable"],
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, LearningDescriptorError):
                raise
            raise LearningDescriptorError(
                "LEARNING_DESCRIPTOR_INVALID",
                "learning descriptor is invalid",
            ) from error

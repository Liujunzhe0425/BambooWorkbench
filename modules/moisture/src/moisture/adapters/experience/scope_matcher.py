"""Deterministic scope matching migrated from the stable legacy implementation."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from moisture.ports.experience_repository import ExperienceMetadata, ExperienceQuery


@dataclass(frozen=True, slots=True)
class ScopeMatch:
    exact_match_count: int
    reasons: tuple[str, ...]


def normalize_scope_value(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _dimension_match(
    name: str, configured: tuple[str, ...], query_value: str | None
) -> tuple[bool, str] | None:
    normalized = {normalize_scope_value(value) for value in configured}
    if "*" in normalized:
        return False, f"{name}:wildcard"
    if query_value is not None and normalize_scope_value(query_value) in normalized:
        return True, f"{name}:exact"
    return None


def match_experience_scope(
    metadata: ExperienceMetadata, query: ExperienceQuery
) -> ScopeMatch | None:
    dimensions = (
        ("supplier", metadata.applicable_suppliers, query.supplier),
        ("material", metadata.applicable_materials, query.material),
        ("season", metadata.applicable_seasons, query.season),
        ("metric", metadata.applicable_metrics, query.metric),
    )
    matches = [
        _dimension_match(name, configured, query_value)
        for name, configured, query_value in dimensions
    ]
    if any(match is None for match in matches):
        return None
    resolved = [match for match in matches if match is not None]
    return ScopeMatch(
        exact_match_count=sum(exact for exact, _ in resolved),
        reasons=tuple(reason for _, reason in resolved),
    )

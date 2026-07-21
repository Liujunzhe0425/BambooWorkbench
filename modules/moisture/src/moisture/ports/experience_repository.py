"""Read-only port and immutable models for governed experience guidance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from moisture.domain.models import BatchRecord

ExperienceStatus = Literal["draft", "pending_review", "approved", "retired"]
EXPERIENCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True, slots=True)
class ExperienceMetadata:
    experience_id: str
    version: str
    status: ExperienceStatus
    title: str
    source: str
    applicable_suppliers: tuple[str, ...]
    applicable_materials: tuple[str, ...]
    applicable_seasons: tuple[str, ...]
    applicable_metrics: tuple[str, ...]
    author: str
    reviewer: str
    evidence_sources: tuple[str, ...]
    effective_at: datetime
    supersedes: str | None

    def __post_init__(self) -> None:
        tuple_fields = (
            "applicable_suppliers",
            "applicable_materials",
            "applicable_seasons",
            "applicable_metrics",
            "evidence_sources",
        )
        for name in tuple_fields:
            values = tuple(getattr(self, name))
            object.__setattr__(self, name, values)
            if not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{name} must contain non-blank strings")
        if re.fullmatch(EXPERIENCE_ID_PATTERN, self.experience_id) is None:
            raise ValueError("invalid experience_id")
        if re.fullmatch(SEMVER_PATTERN, self.version) is None:
            raise ValueError("invalid semantic version")
        if self.supersedes is not None and re.fullmatch(SEMVER_PATTERN, self.supersedes) is None:
            raise ValueError("invalid supersedes version")
        if self.status not in {"draft", "pending_review", "approved", "retired"}:
            raise ValueError("invalid experience status")
        for name in ("title", "source", "author", "reviewer"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at must include a timezone")
        same_reviewer = self.author.strip().casefold() == self.reviewer.strip().casefold()
        if self.status == "approved" and same_reviewer:
            raise ValueError("approved experience author and reviewer must differ")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperienceQuery:
    supplier: str | None = None
    material: str | None = None
    season: str | None = None
    metric: str
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("metric must not be blank")
        if self.as_of is not None and (
            self.as_of.tzinfo is None or self.as_of.utcoffset() is None
        ):
            raise ValueError("as_of must include a timezone")

    @classmethod
    def from_record(
        cls, record: BatchRecord, metric: str, *, as_of: datetime | None = None
    ) -> ExperienceQuery:
        observed = record.arrival_date or record.test_date
        season = None
        if observed is not None:
            if observed.month in {3, 4, 5}:
                season = "spring"
            elif observed.month in {6, 7, 8}:
                season = "summer"
            elif observed.month in {9, 10, 11}:
                season = "autumn"
            else:
                season = "winter"
        return cls(
            supplier=record.supplier,
            material=record.material_type,
            season=season,
            metric=metric,
            as_of=as_of,
        )


@dataclass(frozen=True, slots=True)
class ExperienceReference(ExperienceMetadata):
    quoted_reference: str
    content_hash: str
    reference_path: str
    match_reasons: tuple[str, ...] = ()
    exact_match_count: int = 0
    can_affect_review: Literal[True] = True
    trust_level: Literal["untrusted_reference_data"] = "untrusted_reference_data"

    def __post_init__(self) -> None:
        super(ExperienceReference, self).__post_init__()
        object.__setattr__(self, "match_reasons", tuple(self.match_reasons))
        if re.fullmatch(r"[0-9a-f]{64}", self.content_hash) is None:
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        if self.status != "approved":
            raise ValueError("only approved experience can become a review reference")


class ExperienceRepository(Protocol):
    def search(self, context: ExperienceQuery) -> list[ExperienceReference]: ...

    def get(self, experience_id: str, version: str) -> ExperienceReference | None: ...

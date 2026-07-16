"""Privacy-minimal candidates for optional framework AI review."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AIReviewCandidate:
    candidate_id: str
    target_field: str
    observed_value: Decimal
    reference_value: Decimal
    relative_deviation: Decimal

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must not be empty")
        if not self.target_field:
            raise ValueError("target_field must not be empty")
        if self.relative_deviation < 0:
            raise ValueError("relative_deviation must be non-negative")

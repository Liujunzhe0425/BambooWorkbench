"""Pure, immutable models for deterministic moisture calculations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from moisture.domain.enums import (
    ConfirmationState,
    DisplayColor,
    ReviewStatus,
    ScreenStatus,
)

DecisionTargetField = Literal[
    "mean",
    "total_average",
    "range_value",
    "minimum",
    "maximum",
    "standard_deviation",
    "median",
    "first_quartile",
    "third_quartile",
    "interquartile_range",
    "maximum_department_average_difference",
    "total_weight_kg",
    "sample_1",
    "sample_2",
    "sample_3",
    "sample_4",
    "sample_5",
    "sample_6",
    "sample_7",
    "sample_8",
    "sample_9",
    "sample_10",
]

ConfirmationKind = Literal[
    "sheet_ambiguity",
    "supplier_mapping",
    "department_mapping",
    "formula_conflict",
    "rule_scope",
]


@dataclass(frozen=True, slots=True)
class BusinessConfirmationIssue:
    """Structured, module-owned ambiguity that requires a business choice."""

    kind: ConfirmationKind
    fingerprint: str
    field: str
    candidates: tuple[str, ...]
    source_file: Path
    sheet: str | None = None
    cell_or_range: str | None = None
    suggested_value: str | None = None
    rule_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if not self.fingerprint:
            raise ValueError("fingerprint must not be empty")
        if not self.field:
            raise ValueError("field must not be empty")
        if not self.candidates:
            raise ValueError("candidates must contain at least one item")


@dataclass(frozen=True, slots=True)
class InputFileIdentity:
    source_file: Path
    fingerprint: str
    input_order: int

    def __post_init__(self) -> None:
        if not self.fingerprint:
            raise ValueError("fingerprint must not be empty")
        if self.input_order < 0:
            raise ValueError("input_order must be non-negative")


@dataclass(frozen=True, slots=True)
class SampleMeasurement:
    sample_index: int
    department_raw: str
    department: str
    source_row: int
    initial_mass: Decimal
    dry_mass: Decimal
    foil_mass: Decimal
    source_moisture_value: Decimal | None
    verified_moisture_value: Decimal | None
    value_used_for_statistics: Decimal | None

    def __post_init__(self) -> None:
        if self.sample_index < 1:
            raise ValueError("sample_index must be at least 1")
        if self.source_row < 1:
            raise ValueError("source_row must be at least 1")


@dataclass(frozen=True, slots=True)
class DepartmentGroup:
    name: str
    sample_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_indices", tuple(self.sample_indices))
        if not self.name:
            raise ValueError("department name must not be empty")
        if not self.sample_indices:
            raise ValueError("sample_indices must contain at least 1 item")


@dataclass(frozen=True, slots=True)
class BatchRecord:
    record_id: str
    samples: tuple[SampleMeasurement, ...]
    source_file: Path | None = None
    source_file_hash: str | None = None
    source_sheet: str | None = None
    supplier_raw: str | None = None
    supplier: str | None = None
    material_type: str | None = None
    arrival_date_raw: str | None = None
    arrival_date: date | None = None
    test_date_raw: str | None = None
    test_date: date | None = None
    total_weight_raw: str | None = None
    total_weight_kg: Decimal | None = None
    departments: tuple[DepartmentGroup, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "samples", tuple(self.samples))
        object.__setattr__(self, "departments", tuple(self.departments))
        if not self.record_id:
            raise ValueError("record_id must not be empty")
        if len(self.samples) < 1:
            raise ValueError("samples must contain at least 1 item")
        if len(self.samples) > 10:
            raise ValueError("samples must contain at most 10 items")

    @classmethod
    def minimal(
        cls,
        record_id: str,
        samples: Sequence[SampleMeasurement],
    ) -> BatchRecord:
        return cls(record_id=record_id, samples=tuple(samples))


@dataclass(frozen=True, slots=True)
class BatchStatistics:
    sample_count: int
    mean: Decimal
    total_average: Decimal
    standard_deviation: Decimal | None
    minimum: Decimal
    maximum: Decimal
    range_value: Decimal
    median: Decimal | None
    first_quartile: Decimal | None
    third_quartile: Decimal | None
    interquartile_range: Decimal | None
    department_averages: Mapping[str, Decimal] = field(default_factory=dict)
    maximum_department_average_difference: Decimal | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.sample_count <= 10:
            raise ValueError("sample_count must be between 1 and 10")


@dataclass(frozen=True, slots=True)
class RuleHit:
    rule_id: str
    message: str
    display_color: DisplayColor = DisplayColor.NONE
    target_field: DecisionTargetField | None = None

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must not be empty")
        if not self.message:
            raise ValueError("message must not be empty")


@dataclass(frozen=True, slots=True)
class ScreeningDecision:
    status: ScreenStatus
    rule_hits: tuple[RuleHit, ...] = ()
    display_color: DisplayColor = DisplayColor.NONE
    reason: str | None = None
    target_field: DecisionTargetField | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_hits", tuple(self.rule_hits))


@dataclass(frozen=True, slots=True)
class AIReviewDecision:
    status: ReviewStatus
    display_color: DisplayColor = DisplayColor.NONE
    confirmation_state: ConfirmationState = ConfirmationState.NOT_REQUIRED
    rationale: str | None = None
    target_field: DecisionTargetField | None = None
    confidence: Decimal | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FormulaVerification:
    status: Literal[
        "matched",
        "mismatch",
        "invalid_denominator",
        "source_result_unavailable",
    ]
    verified_value: Decimal | None
    value_used: Decimal | None

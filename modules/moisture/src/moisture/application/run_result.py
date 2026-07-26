"""Contract-independent outcome of one moisture module invocation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class ReviewState(StrEnum):
    """Business review states; contract severity is assigned at the boundary."""

    SUSPECT_HIGH = "suspect_high"
    SUSPECT_LOW = "suspect_low"
    HIGH_SUSPICION_HIGH = "high_suspicion_high"
    HIGH_SUSPICION_LOW = "high_suspicion_low"


@dataclass(frozen=True, slots=True)
class InternalAnomaly:
    anomaly_id: str
    review_state: ReviewState
    field: str
    message: str
    source_file: Path
    sheet: str | None = None
    cell_or_range: str | None = None
    value: Any = None
    rule_id: str | None = None
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class InternalOutput:
    type: str
    path: Path
    label: str
    mime_type: str


@dataclass(frozen=True, slots=True)
class InternalMoistureRunResult:
    """Internal run data before any framework contract choices are applied."""

    job_id: str
    phase: str
    input_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    started_at: datetime
    finished_at: datetime
    root_job_id: str | None = None
    rule_version: str | None = None
    anomalies: tuple[InternalAnomaly, ...] = ()
    confirmations: tuple[Mapping[str, Any], ...] = ()
    outputs: tuple[InternalOutput, ...] = ()
    monthly_snapshot: Mapping[str, Any] | None = None
    file_results: tuple[Mapping[str, Any], ...] = ()
    service_requests: tuple[Mapping[str, Any], ...] = ()
    analysis_summary: str | None = None
    errors: tuple[str, ...] = ()
    cancelled: bool = False
    business_failed: bool = False

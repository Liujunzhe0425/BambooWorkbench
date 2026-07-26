"""Narrow internal writer models and ports.

These types deliberately remain independent from the BambooWorkbench machine
contract.  Application orchestration can assemble a report from domain results
without exposing a framework DTO to the reporting adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from moisture.domain.enums import ConfirmationState, DisplayColor
from moisture.domain.models import (
    AIReviewDecision,
    BatchRecord,
    BatchStatistics,
    ScreeningDecision,
)


@dataclass(frozen=True, slots=True)
class ExperienceCitation:
    entry_id: str
    version: str
    title: str
    source: str
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeCitation:
    record_id: str
    namespace: str
    title: str
    content: str
    source: str


@dataclass(frozen=True, slots=True)
class WorkbookBatch:
    record: BatchRecord
    statistics: BatchStatistics
    screening_decision: ScreeningDecision
    ai_review: AIReviewDecision
    final_display_color: DisplayColor
    confirmation_state: ConfirmationState
    rule_version: str
    review_suggestion: str
    rule_hash: str = ""
    rule_applicable_scope: str = ""
    rule_confirmation_status: str = ""
    lower_threshold: Decimal | None = None
    upper_threshold: Decimal | None = None
    experience_references: tuple[ExperienceCitation, ...] = ()
    ai_degradation_reason: str | None = None
    screening_decisions: tuple[ScreeningDecision, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "experience_references", tuple(self.experience_references))
        decisions = tuple(self.screening_decisions)
        if not decisions and self.screening_decision.status.value != "normal":
            decisions = (self.screening_decision,)
        object.__setattr__(self, "screening_decisions", decisions)


@dataclass(frozen=True, slots=True)
class WorkbookReport:
    started_at: datetime
    batches: tuple[WorkbookBatch, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "batches", tuple(self.batches))


class SummaryWorkbookWriterPort(Protocol):
    def write(self, report: WorkbookReport, output_dir: Path) -> Path: ...

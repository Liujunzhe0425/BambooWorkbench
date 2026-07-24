"""Narrow read models for validated module-generated summary workbooks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from moisture.ports.writers import WorkbookBatch

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SummaryFormat(StrEnum):
    V1_0_0_FIVE_SHEET = "1.0.0-five-sheet"
    V1_0_1_FOUR_SHEET = "1.0.1-four-sheet"


@dataclass(frozen=True, slots=True)
class HistoricalSummarySnapshot:
    """A validated, immutable view of one standard moisture summary."""

    format_version: SummaryFormat
    source_sha256: str
    source_display_name: str
    batches: tuple[WorkbookBatch, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "batches", tuple(self.batches))
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256")
        if (
            not self.source_display_name
            or "/" in self.source_display_name
            or "\\" in self.source_display_name
            or any(ord(character) < 32 for character in self.source_display_name)
        ):
            raise ValueError("source_display_name must be a safe file name")
        record_ids = [batch.record.record_id for batch in self.batches]
        if not record_ids:
            raise ValueError("historical summary must contain at least one batch")
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("historical summary contains duplicate record IDs")


class HistorySummaryReaderPort(Protocol):
    def read(self, source: Path) -> HistoricalSummarySnapshot: ...

"""Narrow input port for source workbook parsing."""

from pathlib import Path
from typing import Protocol

from moisture.domain.models import BatchRecord


class WorkbookParserPort(Protocol):
    def parse(self, path: Path, default_year: int | None = None) -> BatchRecord:
        """Parse a source workbook without modifying it."""
        ...

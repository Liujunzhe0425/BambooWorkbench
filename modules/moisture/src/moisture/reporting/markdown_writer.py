"""Render the auditable, human-readable moisture analysis report."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from moisture.ports.writers import ExperienceCitation, KnowledgeCitation, WorkbookBatch
from moisture.runtime_paths import module_root


@dataclass(frozen=True, slots=True)
class AnalysisReportView:
    """Narrow reporting input, independent of framework contract models."""

    started_at: datetime
    status: str
    batches: tuple[WorkbookBatch, ...]
    rule_version: str
    rule_hash: str
    rule_source: str
    rule_confirmation_status: str
    candidate_total: int
    candidate_sent: int
    candidate_omitted: int
    knowledge_citations: tuple[KnowledgeCitation, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "batches", tuple(self.batches))
        object.__setattr__(self, "knowledge_citations", tuple(self.knowledge_citations))
        object.__setattr__(self, "errors", tuple(self.errors))
        candidate_counts = (
            self.candidate_total,
            self.candidate_sent,
            self.candidate_omitted,
        )
        if any(count < 0 for count in candidate_counts):
            raise ValueError("candidate counts must be non-negative")
        if self.candidate_sent + self.candidate_omitted != self.candidate_total:
            raise ValueError("candidate counts must satisfy sent + omitted = total")

    @property
    def rule_confirmation_label(self) -> str:
        labels = {
            "confirmed": "已确认",
            "pending_confirmation": "待业务确认",
        }
        return labels.get(self.rule_confirmation_status, self.rule_confirmation_status)

    @property
    def experience_citations(self) -> tuple[tuple[str, ExperienceCitation], ...]:
        return tuple(
            (batch.record.record_id, citation)
            for batch in self.batches
            for citation in batch.experience_references
        )

    @property
    def reviewed_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(batch for batch in self.batches if batch.ai_review.rationale)

    @property
    def degraded_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(batch for batch in self.batches if batch.ai_degradation_reason)


def _template_directory() -> Path:
    return module_root() / "templates"


def _render(report: AnalysisReportView) -> str:
    environment = Environment(
        loader=FileSystemLoader(_template_directory()),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    environment.globals.clear()
    template = environment.get_template("analysis_report.md.j2")
    rendered = template.render(report=report)
    return rendered if rendered.endswith("\n") else f"{rendered}\n"


def _atomic_write_text(destination: Path, text: str) -> None:
    temporary = destination.with_name(f".analysis_report-{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_analysis_markdown(report: AnalysisReportView, output_dir: Path) -> Path:
    """Write ``analysis_report.md`` atomically inside *output_dir*."""

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "analysis_report.md"
    _atomic_write_text(destination, _render(report))
    return destination

"""Render the auditable, human-readable moisture analysis report."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from moisture.domain.enums import ConfirmationState, ScreenStatus
from moisture.ports.writers import ExperienceCitation, KnowledgeCitation, WorkbookBatch
from moisture.reporting.labels import color_label, screen_label
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
    rule_applicable_scope: str
    rule_confirmation_status: str
    candidate_total: int
    candidate_sent: int
    candidate_omitted: int
    input_count: int | None = None
    processed_count: int | None = None
    skipped_count: int = 0
    failed_count: int = 0
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
        run_counts = (
            self.input_count,
            self.processed_count,
            self.skipped_count,
            self.failed_count,
        )
        if any(count is not None and count < 0 for count in run_counts):
            raise ValueError("run counts must be non-negative")

    @property
    def rule_confirmation_label(self) -> str:
        labels = {
            "confirmed": "已确认",
            "pending_confirmation": "待业务确认",
        }
        return labels.get(self.rule_confirmation_status, self.rule_confirmation_status)

    @property
    def status_label(self) -> str:
        labels = {
            "success": "成功",
            "partial_success": "部分成功",
            "failed": "失败",
            "needs_confirmation": "等待人工确认",
        }
        return labels.get(self.status, self.status)

    @staticmethod
    def screening_label(batch: WorkbookBatch) -> str:
        return screen_label(batch.screening_decision.status)

    @staticmethod
    def screening_reason(batch: WorkbookBatch) -> str:
        return batch.screening_decision.reason or batch.review_suggestion

    @staticmethod
    def color_label(batch: WorkbookBatch) -> str:
        return color_label(batch.ai_review.display_color)

    @staticmethod
    def format_percent(value: Decimal | None) -> str:
        if value is None:
            return "无适用规则"
        return f"{value * Decimal('100'):.2f}%"

    @staticmethod
    def is_pending(batch: WorkbookBatch) -> bool:
        return batch.confirmation_state == ConfirmationState.PENDING_HUMAN_REVIEW

    @staticmethod
    def review_advice(batch: WorkbookBatch) -> str:
        if batch.review_suggestion:
            return batch.review_suggestion
        advice = {
            ScreenStatus.HIGH: "建议复核称量记录、样本状态及检测过程。",
            ScreenStatus.LOW: "建议复核称量记录、样本状态及检测过程。",
            ScreenStatus.DATA_QUALITY: "建议补齐或修正源数据后重新检测。",
        }
        return advice.get(batch.screening_decision.status, "建议按现行业务流程复核。")

    @property
    def successful_count(self) -> int:
        return self.processed_count if self.processed_count is not None else len(self.batches)

    @property
    def total_input_count(self) -> int:
        if self.input_count is not None:
            return self.input_count
        return self.successful_count + self.skipped_count + self.failed_count

    @property
    def normal_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(
            batch
            for batch in self.batches
            if batch.screening_decision.status == ScreenStatus.NORMAL and not self.is_pending(batch)
        )

    @property
    def high_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(
            batch for batch in self.batches if batch.screening_decision.status == ScreenStatus.HIGH
        )

    @property
    def low_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(
            batch for batch in self.batches if batch.screening_decision.status == ScreenStatus.LOW
        )

    @property
    def data_quality_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(
            batch
            for batch in self.batches
            if batch.screening_decision.status == ScreenStatus.DATA_QUALITY
        )

    @property
    def pending_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(batch for batch in self.batches if self.is_pending(batch))

    @property
    def detailed_batches(self) -> tuple[WorkbookBatch, ...]:
        return tuple(
            batch
            for batch in self.batches
            if batch.screening_decision.status != ScreenStatus.NORMAL or self.is_pending(batch)
        )

    @property
    def threshold_pairs(self) -> tuple[tuple[Decimal | None, Decimal | None], ...]:
        pairs: list[tuple[Decimal | None, Decimal | None]] = []
        for batch in self.batches:
            pair = (batch.lower_threshold, batch.upper_threshold)
            if pair not in pairs:
                pairs.append(pair)
        return tuple(pairs)

    @property
    def public_errors(self) -> tuple[str, ...]:
        absolute_path = re.compile(r"(?:[A-Za-z]:[\\/]|/)")
        return tuple(
            "处理失败，详情请查看任务错误记录。"
            if "\n" in error or "\r" in error or absolute_path.search(error)
            else error
            for error in self.errors
        )

    @property
    def has_data_quality_risks(self) -> bool:
        return bool(self.errors or self.data_quality_batches)

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

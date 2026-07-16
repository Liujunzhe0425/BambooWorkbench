from __future__ import annotations

# ruff: noqa: E402, I001

import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.domain.enums import (
    ConfirmationState,
    DisplayColor,
    ReviewStatus,
    ScreenStatus,
)
from moisture.domain.models import (
    AIReviewDecision,
    BatchRecord,
    BatchStatistics,
    SampleMeasurement,
    ScreeningDecision,
)
from moisture.ports.writers import ExperienceCitation, WorkbookBatch
from moisture.reporting import markdown_writer
from moisture.reporting.markdown_writer import AnalysisReportView, write_analysis_markdown


def _batch(
    record_id: str,
    color: DisplayColor,
    *,
    experience: bool = False,
    degradation: str | None = None,
) -> WorkbookBatch:
    value = Decimal("0.61") if color in {DisplayColor.ORANGE, DisplayColor.RED} else Decimal("0.44")
    sample = SampleMeasurement(
        sample_index=1,
        department_raw="品质",
        department="品质",
        source_row=5,
        initial_mass=Decimal("100"),
        dry_mass=Decimal("52"),
        foil_mass=Decimal("4"),
        source_moisture_value=value,
        verified_moisture_value=value,
        value_used_for_statistics=value,
    )
    record = BatchRecord(
        record_id=record_id,
        samples=(sample,),
        source_file=Path(f"{record_id}.xlsx"),
        source_file_hash="a" * 64,
        source_sheet="检测数据",
        supplier="供应商甲",
        material_type="竹丝",
    )
    statistics = BatchStatistics(
        sample_count=1,
        mean=value,
        total_average=value,
        standard_deviation=None,
        minimum=value,
        maximum=value,
        range_value=Decimal("0"),
        median=value,
        first_quartile=value,
        third_quartile=value,
        interquartile_range=Decimal("0"),
    )
    direction = (
        ScreenStatus.HIGH if color in {DisplayColor.ORANGE, DisplayColor.RED} else ScreenStatus.LOW
    )
    screening_color = DisplayColor.ORANGE if direction == ScreenStatus.HIGH else DisplayColor.GREEN
    reviewed = color in {DisplayColor.RED, DisplayColor.BLUE}
    return WorkbookBatch(
        record=record,
        statistics=statistics,
        screening_decision=ScreeningDecision(
            status=direction,
            display_color=screening_color,
            reason="确定性规则发现疑似偏离",
            target_field="mean",
        ),
        ai_review=AIReviewDecision(
            status=(
                ReviewStatus.REVIEW_HIGH if color == DisplayColor.RED else ReviewStatus.REVIEW_LOW
            )
            if reviewed
            else ReviewStatus.NOT_COMPLETED,
            display_color=color if reviewed else DisplayColor.NONE,
            confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
            rationale="辅助证据支持高度疑似" if reviewed else None,
            target_field="mean" if reviewed else None,
            confidence=Decimal("0.86") if reviewed else None,
        ),
        final_display_color=color,
        confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
        rule_version="rules-v1",
        review_suggestion="建议复核测量与来源记录",
        lower_threshold=Decimal("0.47"),
        upper_threshold=Decimal("0.55"),
        experience_references=(
            (
                ExperienceCitation(
                    "EXP-001",
                    "1.2.0",
                    "夏季复核经验",
                    "experience/approved/exp-001.md",
                ),
            )
            if experience
            else ()
        ),
        ai_degradation_reason=degradation,
    )


@pytest.fixture
def report() -> AnalysisReportView:
    return AnalysisReportView(
        started_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        status="partial_success",
        batches=(
            _batch("R1", DisplayColor.ORANGE, experience=True, degradation="AI 服务超时"),
            _batch("R2", DisplayColor.GREEN),
            _batch("R3", DisplayColor.RED),
            _batch("R4", DisplayColor.BLUE),
        ),
        rule_version="rules-v1",
        rule_hash="b" * 64,
        rule_source="rules/active/rule-package.json",
        rule_confirmation_status="pending_confirmation",
        candidate_total=7,
        candidate_sent=4,
        candidate_omitted=3,
        errors=("一个输入文件未能解析，其他文件已继续处理",),
    )


def test_report_separates_deterministic_and_auxiliary_evidence(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    output = write_analysis_markdown(report, tmp_path / "output")
    text = output.read_text(encoding="utf-8")

    assert output == tmp_path / "output" / "analysis_report.md"
    for heading in (
        "## 确定性分析结果",
        "## 规则快照与适用状态",
        "## 已审核经验引用",
        "## 辅助服务记录与降级",
        "## 颜色语义与使用限制",
    ):
        assert heading in text
    assert "rules-v1" in text
    assert "b" * 64 in text
    assert "rules/active/rule-package.json" in text
    assert "待业务确认" in text
    assert "EXP-001" in text and "1.2.0" in text
    assert "候选总数：7；发送数：4；省略数：3" in text
    assert "AI 服务超时" in text


def test_report_explains_orange_green_red_blue_without_formal_conclusion(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    text = write_analysis_markdown(report, tmp_path).read_text(encoding="utf-8")

    assert "橙色：确定性规则发现偏高疑似" in text
    assert "绿色：确定性规则发现偏低疑似" in text
    assert "红色：有效辅助证据支持的高度偏高疑似" in text
    assert "蓝色：有效辅助证据支持的高度偏低疑似" in text
    assert "均不表示正式错误、不合格或责任认定" in text


def test_report_contains_no_responsibility_conclusion_prompt(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    text = write_analysis_markdown(report, tmp_path).read_text(encoding="utf-8")

    for forbidden in ("责任结论", "责任判定", "责任人", "最终结论由", "API Key", "Provider"):
        assert forbidden not in text


def test_report_handles_empty_experience_and_no_degradation(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    batches = tuple(
        replace(batch, experience_references=(), ai_degradation_reason=None)
        for batch in report.batches
    )
    clean = replace(report, batches=batches, errors=())
    text = write_analysis_markdown(clean, tmp_path).read_text(encoding="utf-8")

    experience = text.split("## 已审核经验引用", 1)[1].split("## 辅助服务记录与降级", 1)[0]
    degradation = text.split("## 辅助服务记录与降级", 1)[1].split("## 数据质量与处理限制", 1)[0]
    assert "- 无已审核经验引用。" in experience
    assert "- 无服务降级记录。" in degradation


def test_view_rejects_inconsistent_candidate_counts(report: AnalysisReportView) -> None:
    with pytest.raises(ValueError, match="candidate"):
        replace(report, candidate_omitted=2)


def test_markdown_is_atomic_and_cleans_temporary_file(
    tmp_path: Path, report: AnalysisReportView, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    destination = output_dir / "analysis_report.md"
    destination.write_text("existing\n", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(markdown_writer.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_analysis_markdown(report, output_dir)

    assert destination.read_text(encoding="utf-8") == "existing\n"
    assert not list(output_dir.glob(".analysis_report-*.tmp"))


def test_markdown_replaces_existing_file_without_leaving_temp(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    destination = output_dir / "analysis_report.md"
    destination.write_text("old\n", encoding="utf-8")

    output = write_analysis_markdown(report, output_dir)

    assert output == destination
    assert output.read_text(encoding="utf-8").startswith("# 竹丝含水率分析报告")
    assert not list(output_dir.glob(".analysis_report-*.tmp"))
    if os.name == "nt":
        assert output.read_bytes().endswith(b"\n")

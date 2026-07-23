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
from moisture.ports.writers import ExperienceCitation, KnowledgeCitation, WorkbookBatch
from moisture.reporting import markdown_writer
from moisture.reporting.markdown_writer import AnalysisReportView, write_analysis_markdown


def _batch(
    record_id: str,
    status: ScreenStatus,
    *,
    pending: bool = False,
    experience: bool = False,
) -> WorkbookBatch:
    values = {
        ScreenStatus.NORMAL: Decimal("0.51"),
        ScreenStatus.HIGH: Decimal("0.61"),
        ScreenStatus.LOW: Decimal("0.44"),
        ScreenStatus.DATA_QUALITY: Decimal("0.50"),
    }
    colors = {
        ScreenStatus.NORMAL: DisplayColor.NONE,
        ScreenStatus.HIGH: DisplayColor.ORANGE,
        ScreenStatus.LOW: DisplayColor.GREEN,
        ScreenStatus.DATA_QUALITY: DisplayColor.NONE,
    }
    reasons = {
        ScreenStatus.NORMAL: "均值处于初筛范围内",
        ScreenStatus.HIGH: "均值超过上限",
        ScreenStatus.LOW: "均值低于下限",
        ScreenStatus.DATA_QUALITY: "有效样本不足",
    }
    value = values[status]
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
        material_type="原竹丝",
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
    confirmation_state = (
        ConfirmationState.PENDING_HUMAN_REVIEW if pending else ConfirmationState.NOT_REQUIRED
    )
    return WorkbookBatch(
        record=record,
        statistics=statistics,
        screening_decision=ScreeningDecision(
            status=status,
            display_color=colors[status],
            reason=reasons[status],
            target_field="mean",
        ),
        ai_review=AIReviewDecision(
            status=ReviewStatus.NOT_COMPLETED,
            display_color=DisplayColor.NONE,
            confirmation_state=confirmation_state,
        ),
        final_display_color=colors[status],
        confirmation_state=confirmation_state,
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
    )


@pytest.fixture
def report() -> AnalysisReportView:
    return AnalysisReportView(
        started_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        status="partial_success",
        batches=(
            _batch("NORMAL-001", ScreenStatus.NORMAL),
            _batch("NORMAL-002", ScreenStatus.NORMAL),
            _batch("HIGH-001", ScreenStatus.HIGH, pending=True, experience=True),
            _batch("LOW-001", ScreenStatus.LOW),
            _batch("QUALITY-001", ScreenStatus.DATA_QUALITY),
        ),
        rule_version="rules-v1",
        rule_hash="b" * 64,
        rule_source="rules/active/rule-package.json",
        rule_applicable_scope="原竹丝；全年",
        rule_confirmation_status="pending_confirmation",
        candidate_total=0,
        candidate_sent=0,
        candidate_omitted=0,
        input_count=6,
        processed_count=5,
        skipped_count=0,
        failed_count=1,
        knowledge_citations=(
            KnowledgeCitation(
                record_id="KN-001",
                namespace="moisture",
                title="复核指引",
                content="检查原始称量记录。",
                source="local_document:guidance.md",
            ),
        ),
        errors=("broken.xlsx: WORKBOOK_PROCESSING_FAILED",),
    )


def _sections(text: str) -> tuple[str, str]:
    customer_body, appendix = text.split("## 技术附录", 1)
    return customer_body, appendix


def test_report_aggregates_normal_batches_and_expands_only_attention_items(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    output = write_analysis_markdown(report, tmp_path / "output")
    text = output.read_text(encoding="utf-8")
    customer_body, _ = _sections(text)

    assert output == tmp_path / "output" / "analysis_report.md"
    assert "输入 6 个，成功处理 5 个，跳过 0 个，失败 1 个" in customer_body
    assert "正常批次：2 个" in customer_body
    assert "偏高疑似批次：1 个" in customer_body
    assert "偏低疑似批次：1 个" in customer_body
    assert "信息不足批次：1 个" in customer_body
    assert "待人工复核 1 个" in customer_body
    assert "NORMAL-001" not in customer_body
    assert "NORMAL-002" not in customer_body
    for record_id in ("HIGH-001", "LOW-001", "QUALITY-001"):
        assert record_id in customer_body
    assert "broken.xlsx" in customer_body


def test_customer_body_centralizes_thresholds_and_hides_technical_trace(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    text = write_analysis_markdown(report, tmp_path).read_text(encoding="utf-8")
    customer_body, appendix = _sections(text)

    assert customer_body.count("均值初筛范围") == 1
    assert "下限 47.00%，上限 55.00%" in customer_body
    assert "61.00%" in customer_body
    assert "0.610000" not in customer_body
    assert "b" * 64 not in customer_body
    assert "rules/active/rule-package.json" not in customer_body
    assert "EXP-001" not in customer_body
    assert "KN-001" not in customer_body
    assert "b" * 64 in appendix
    assert "rules/active/rule-package.json" in appendix
    assert "EXP-001" in appendix
    assert "Knowledge `moisture/KN-001`" in appendix


def test_report_sanitizes_customer_errors_and_avoids_empty_warning_section(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    unsafe = replace(report, errors=("C:\\customer\\bad.xlsx: Traceback: parser failed",))
    text = write_analysis_markdown(unsafe, tmp_path / "unsafe").read_text(encoding="utf-8")

    assert "C:\\customer" not in text
    assert "Traceback" not in text
    assert "处理失败，详情请查看任务错误记录。" in text

    normal_only = replace(
        report,
        status="success",
        batches=(_batch("NORMAL-ONLY", ScreenStatus.NORMAL),),
        input_count=1,
        processed_count=1,
        failed_count=0,
        knowledge_citations=(),
        errors=(),
    )
    clean_text = write_analysis_markdown(normal_only, tmp_path / "clean").read_text(
        encoding="utf-8"
    )
    customer_body, _ = _sections(clean_text)
    assert "NORMAL-ONLY" not in customer_body
    assert "## 数据质量风险" not in customer_body
    assert "未记录数据质量问题" not in customer_body


def test_report_keeps_business_boundary_and_deterministic_color_meaning(
    tmp_path: Path, report: AnalysisReportView
) -> None:
    text = write_analysis_markdown(report, tmp_path).read_text(encoding="utf-8")

    assert "不替代质量放行、处置或责任认定" in text
    assert "橙色：确定性规则发现偏高疑似" in text
    assert "绿色：确定性规则发现偏低疑似" in text
    assert "红色：" not in text
    assert "蓝色：" not in text
    for forbidden in ("API Key", "Provider", "原始 JSON"):
        assert forbidden not in text


def test_view_rejects_inconsistent_candidate_or_run_counts(
    report: AnalysisReportView,
) -> None:
    with pytest.raises(ValueError, match="candidate"):
        replace(report, candidate_omitted=2)
    with pytest.raises(ValueError, match="run counts"):
        replace(report, failed_count=-1)


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

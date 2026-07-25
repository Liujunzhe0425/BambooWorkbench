from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent.cli import run_job  # noqa: E402
from after_sales_agent.extractor import (  # noqa: E402
    fallback_reason_summary,
    infer_date,
    process_workbook,
)
from after_sales_agent.normalizer import (  # noqa: E402
    analyze_fee_text,
    determine_fee,
    safe_calculate,
)
from after_sales_agent.report import write_summary_workbook  # noqa: E402
from after_sales_agent.rules import load_rules  # noqa: E402


def test_rule_fallback_prefers_root_cause_over_first_symptom() -> None:
    summary = fallback_reason_summary(
        {
            "investigation": (
                "客户安装使用过程中，板材跌落造成断裂。"
                "断裂层面未涂胶，且此批板材间隙过多，属于工厂质量问题。"
            )
        },
        ["性能", "加工"],
    )
    assert "未涂胶" in summary
    assert "质量问题" in summary


def test_final_solution_cost_brand_and_processing_status_take_priority(
    tmp_path: Path,
) -> None:
    source = tmp_path / "FZ示例桃花江-项目.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "售后单"
    sheet.append(["客户/项目", "脱敏项目客户"])
    sheet.append(["投诉日期", "2026-07-05"])
    sheet.append(["反馈内容", "栏杆立柱和横梁开裂"])
    sheet.append(["方案申请明细", "客户要求补板"])
    sheet.append(
        [
            "售后负责人调查情况",
            "低温下竹木收缩大于内部金属柱导致胀裂。方案一修补合计4100元；"
            "方案二补数材料5760元。",
        ]
    )
    sheet.append(["售后解决方案", "最终按方案二执行，重新生产补齐数量，材料费用5760元。"])
    workbook.save(source)

    record, anomalies, _confirmations = process_workbook(source, load_rules(MODULE_ROOT))

    assert not anomalies
    assert record is not None
    assert record["brand"] == "桃花江"
    assert record["primary_issue_type"] == "性能"
    assert "收缩" in record["issue_reason_summary"]
    assert record["cost"] == 5760
    assert "售后解决方案" in record["cost_evidence"]
    assert record["resolution_status"] == "处理中"


def test_master_report_keeps_multilabel_flags_in_one_case_row(tmp_path: Path) -> None:
    records = [
        {
            "year": 2026,
            "month": 1,
            "brand": "桃花江",
            "issue_types": ["性能", "加工"],
            "primary_issue_type": "加工",
            "cost": 100,
            "cost_included": True,
            "closed": True,
        }
    ]
    output = tmp_path / "summary.xlsx"
    write_summary_workbook(records, output, load_rules(MODULE_ROOT))
    workbook = openpyxl.load_workbook(output, data_only=False)
    sheet = workbook["售后全量总表"]
    headers = {sheet.cell(3, col).value: col for col in range(1, sheet.max_column + 1)}
    assert sheet.max_row == 4
    assert sheet.cell(4, headers["性能"]).value == "是"
    assert sheet.cell(4, headers["加工"]).value == "是"
    assert sheet.cell(4, headers["主要原因"]).value == "加工"


def test_summary_includes_every_year_and_dynamic_brand(tmp_path: Path) -> None:
    records = [
        {
            "year": 2025,
            "month": 12,
            "brand": "未知",
            "primary_issue_type": "加工",
            "cost": 360,
            "cost_included": True,
            "resolution_status": "处理中",
        },
        {
            "year": 2026,
            "month": 1,
            "brand": "清竹",
            "primary_issue_type": "性能",
            "cost": 648,
            "cost_included": True,
            "resolution_status": "已解决",
        },
    ]
    output = tmp_path / "all-years.xlsx"
    write_summary_workbook(records, output, load_rules(MODULE_ROOT))
    workbook = openpyxl.load_workbook(output, data_only=True)
    sheet = workbook["售后全量总表"]
    headers = {sheet.cell(3, col).value: col for col in range(1, sheet.max_column + 1)}
    assert sheet.max_row == 5
    assert sheet.cell(4, headers["品牌"]).value == "未知"
    assert sheet.cell(5, headers["品牌"]).value == "清竹"


def test_unknown_brand_keeps_customer_separate_and_extracts_reason(tmp_path: Path) -> None:
    source = tmp_path / "未知品牌.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "售后单"
    sheet.append(["客户/项目", "脱敏示例客户"])
    sheet.append(["投诉日期", "2026-07-01"])
    sheet.append(["反馈内容", "现场无法安装"])
    sheet.append(["售后调查", "开片指令错误，宽度加工少了5毫米"])
    sheet.append(["解决方案", "已返工"])
    workbook.save(source)

    record, anomalies, confirmations = process_workbook(source, load_rules(MODULE_ROOT))

    assert not anomalies
    assert record is not None
    assert record["brand"] == "未知"
    assert record["customer"] == "脱敏示例客户"
    assert record["primary_issue_type"] == "加工"
    assert "开片指令错误" in record["issue_reason_summary"]
    assert not any(item["field"] == "brand" for item in confirmations)


def test_every_input_has_one_record_including_duplicates_and_failures(
    tmp_path: Path,
) -> None:
    input_a = tmp_path / "重复A.xlsx"
    input_b = tmp_path / "重复B.xlsx"
    broken = tmp_path / "损坏文件.xlsx"
    output_dir = tmp_path / "output"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "售后单"
    sheet.append(["客户/项目", "脱敏输入客户"])
    sheet.append(["投诉日期", "2026-07-02"])
    sheet.append(["反馈内容", "板材开裂"])
    sheet.append(["解决方案", "已更换，合计费用500元"])
    workbook.save(input_a)
    input_b.write_bytes(input_a.read_bytes())
    broken.write_text("not-an-xlsx", encoding="utf-8")
    job = {
        "schema_version": "1.0",
        "job_id": "all-inputs",
        "module_id": "after_sales",
        "phase": "draft",
        "run_mode": "batch",
        "input_files": [str(input_a), str(input_b), str(broken)],
        "output_dir": str(output_dir),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")

    assert run_job(job_path) == 0
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    records = json.loads((output_dir / "after_sales_records.json").read_text(encoding="utf-8"))
    assert result["summary"]["processed_count"] == 2
    assert result["summary"]["failed_count"] == 1
    assert len(result["file_results"]) == len(records) == 3
    assert records[0]["file_sha256"] == records[1]["file_sha256"]
    assert records[2]["analysis_status"] == "分析失败"
    assert records[2]["error_code"] == "WORKBOOK_INVALID_OR_CORRUPTED"
    assert result["service_requests"]


def test_date_uses_quality_date_and_never_delivery_or_filename() -> None:
    fields = {
        "complaint_date": "8月25号",
        "order_no": "DEMO20250101-001",
        "delivery_date": "2025-07-17",
    }
    normalized, year, month, confidence = infer_date(fields, Path("ignored.xlsx"))
    assert normalized == "8月25日"
    assert year is None
    assert month == 8
    assert confidence >= 0.8

    fields["complaint_date"] = ""
    assert infer_date(fields, Path("2026年7月文件.xlsx")) == (None, None, None, 0.0)


def test_unknown_and_transferred_fees_remain_null_not_zero() -> None:
    rules = load_rules(MODULE_ROOT)
    missing = determine_fee({"solution": "已安排返工，费用未注明"}, rules)
    transferred = determine_fee({"solution": "售后费用并入其他订单并由供应商承担"}, rules)
    assert missing.amount is None
    assert missing.status == "not_found"
    assert transferred.amount is None
    assert transferred.status == "transferred"


def test_safe_fee_calculation_and_multiple_items() -> None:
    assert safe_calculate("1100.4+11738.4-(440*12.87)") == 7176
    result = analyze_fee_text(
        "损失：1.86*0.139*0.038*8000*7=550.17元；"
        "1.86*0.196*0.038*8000*7=775.7元",
        "售后解决方案",
        load_rules(MODULE_ROOT),
    )
    assert result.amount == 1325.87
    assert result.status == "calculated"


def test_source_cells_are_kept_for_auditable_fields(tmp_path: Path) -> None:
    source = tmp_path / "source-cells.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "售后单"
    sheet.append(["反馈内容", "板材开裂"])
    sheet.append(["售后解决方案", "材料合计费用648元"])
    workbook.save(source)
    record, anomalies, _confirmations = process_workbook(source, load_rules(MODULE_ROOT))
    assert not anomalies
    assert record is not None
    assert record["source_cells"]["feedback"] == "B1"
    assert record["source_cells"]["solution"] == "B2"
    assert record["fee_amount"] == 648


def test_master_report_contains_required_review_statuses(tmp_path: Path) -> None:
    records = [
        {
            "input_index": 1,
            "source_file": "sample.xlsx",
            "included_in_summary": True,
            "year": 2026,
            "month": 1,
            "brand": "未知",
            "primary_issue_type": "性能",
            "fee_amount": None,
            "cost": None,
            "cost_included": False,
            "fee_status": "not_found",
            "case_status": "待确认",
            "resolution_status": "未解决",
            "needs_review": True,
            "warnings": ["费用待确认"],
            "source_cells": {"feedback": "B6:D6"},
        }
    ]
    output = tmp_path / "required-review.xlsx"
    write_summary_workbook(records, output, load_rules(MODULE_ROOT))
    workbook = openpyxl.load_workbook(output, data_only=False)
    summary = workbook["售后全量总表"]
    headers = {summary.cell(3, col).value: col for col in range(1, summary.max_column + 1)}
    assert summary.cell(4, headers["售后费用复核状态"]).value == "待复核"
    assert summary.cell(4, headers["责任工厂复核状态"]).value == "待复核"
    assert summary.cell(4, headers["纳入业务汇总"]).value == "是"

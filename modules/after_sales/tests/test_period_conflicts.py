from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent.cli import (  # noqa: E402
    TASK_PERIOD_SCOPE_FIELD,
    TASK_PERIOD_SCOPE_VALUE,
    TASK_PERIOD_UNRESOLVED_CODE,
    TASK_PERIOD_ZERO_MATCH_CODE,
    run_job,
)
from framework_ai_helpers import write_service_response  # noqa: E402

from core.contracts.result import ModuleResult  # noqa: E402


def _make_workbook(
    path: Path,
    *,
    complaint_date: str,
    customer: str = "不应出现在年月冲突说明中的脱敏客户",
) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "售后单"
    rows = [
        ["客户/项目", customer],
        ["提出质量问题日期", complaint_date],
        ["产品名称", "桃花江竹地板"],
        ["反馈内容", "竹地板出现开裂。"],
        ["售后负责人调查情况", "含水率变化导致收缩开裂。"],
        ["售后解决方案", "已完成更换，企业售后成本1000元。"],
    ]
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def _job(
    inputs: list[Path],
    output_dir: Path,
    *,
    year: int,
    month: int,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "period-draft",
        "module_id": "after_sales",
        "phase": "draft",
        "run_mode": "batch" if len(inputs) > 1 else "single",
        "input_files": [str(path.resolve()) for path in inputs],
        "output_dir": str(output_dir.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
        "task_name": "脱敏年月冲突验收",
        "period_year": year,
        "period_month": month,
        "learning_enabled": True,
    }
    payload.update(overrides)
    return payload


def _run(tmp_path: Path, payload: dict[str, object], name: str) -> dict[str, object]:
    job_path = tmp_path / f"{name}.json"
    job_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert run_job(job_path) == 0
    output_dir = Path(str(payload["output_dir"]))
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    ModuleResult.model_validate(result)
    return result


def _bind_framework_ai(
    tmp_path: Path,
    payload: dict[str, object],
    name: str,
) -> dict[str, object]:
    first = _run(tmp_path, payload, f"{name}-first")
    assert first["service_requests"]
    response_path = write_service_response(
        tmp_path / f"{name}-service-response.json",
        first["service_requests"],
        task_id=str(payload["job_id"]),
        status="error",
    )
    return _run(
        tmp_path,
        {
            **payload,
            "ai_enabled": True,
            "service_response_file": str(response_path.resolve()),
        },
        f"{name}-bound",
    )


def _confirmation_value(prompt: dict[str, object]) -> object:
    field = str(prompt["field"])
    if field == TASK_PERIOD_SCOPE_FIELD:
        return TASK_PERIOD_SCOPE_VALUE
    if field == "complaint_date":
        return "2026-04-10"
    if field == "售后费用":
        return 1000
    if field == "责任工厂":
        return "一厂"
    if field == "投诉类型":
        return "性能"
    return prompt.get("suggested_value")


def _confirmation_file(path: Path, draft: dict[str, object]) -> Path:
    prompts = draft["confirmations"]
    assert isinstance(prompts, list)
    payload = {
        "schema_version": "1.0",
        "job_id": "period-draft",
        "answers": [
            {
                "confirmation_id": prompt["confirmation_id"],
                "value": _confirmation_value(prompt),
            }
            for prompt in prompts
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_definitive_zero_match_stops_before_ai_and_formal_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "跨月脱敏样表.xlsx"
    _make_workbook(source, complaint_date="2025-05-10")
    output = tmp_path / "zero-output"

    result = _run(
        tmp_path,
        _job([source], output, year=2026, month=4),
        "zero-match",
    )

    assert result["status"] == "failed"
    assert result["service_requests"] == []
    assert result["confirmations"] == []
    assert result["outputs"] == []
    assert any(TASK_PERIOD_ZERO_MATCH_CODE in error for error in result["errors"])
    assert {path.name for path in output.iterdir()} == {"result.json"}
    conflict = next(
        item
        for item in result["anomalies"]
        if item["rule_id"] == "AFTER_SALES_TASK_PERIOD_CONFLICT"
    )
    public_text = json.dumps(
        {"anomaly": conflict, "errors": result["errors"]},
        ensure_ascii=False,
    )
    assert "2026年4月" in public_text
    assert "2025年5月1条" in public_text
    assert "不应出现在年月冲突说明中的脱敏客户" not in public_text
    assert str(tmp_path) not in public_text
    assert "竹地板出现开裂" not in public_text


def test_all_records_matching_target_continue_normal_draft(tmp_path: Path) -> None:
    first = tmp_path / "目标月一.xlsx"
    second = tmp_path / "目标月二.xlsx"
    _make_workbook(first, complaint_date="2026-04-10")
    _make_workbook(second, complaint_date="2026-04-20")

    result = _run(
        tmp_path,
        _job([first, second], tmp_path / "all-match", year=2026, month=4),
        "all-match",
    )

    assert result["status"] == "success"
    assert result["service_requests"]
    assert not any(
        item["rule_id"] == "AFTER_SALES_TASK_PERIOD_CONFLICT"
        for item in result["anomalies"]
    )


def test_partial_cross_month_and_cross_year_preserve_dates_and_snapshot_target_only(
    tmp_path: Path,
) -> None:
    target = tmp_path / "目标月.xlsx"
    other_month = tmp_path / "同年其他月.xlsx"
    other_year = tmp_path / "跨年.xlsx"
    _make_workbook(target, complaint_date="2026-04-10")
    _make_workbook(other_month, complaint_date="2026-05-10")
    _make_workbook(other_year, complaint_date="2025-04-10")
    draft_output = tmp_path / "partial-draft"
    payload = _job(
        [target, other_month, other_year],
        draft_output,
        year=2026,
        month=4,
    )
    draft = _bind_framework_ai(tmp_path, payload, "partial")
    fields = [prompt["field"] for prompt in draft["confirmations"]]
    assert fields.count(TASK_PERIOD_SCOPE_FIELD) == 1
    assert draft["status"] == "needs_confirmation"

    confirmation_path = _confirmation_file(tmp_path / "partial-confirm.json", draft)
    final_output = tmp_path / "partial-final"
    final = _run(
        tmp_path,
        {
            **payload,
            "job_id": "period-final",
            "phase": "finalize",
            "output_dir": str(final_output.resolve()),
            "parent_job_id": "period-draft",
            "confirmation_file": str(confirmation_path.resolve()),
            "service_response_file": None,
        },
        "partial-final",
    )

    assert final["status"] == "success"
    records = json.loads(
        (final_output / "after_sales_records.json").read_text(encoding="utf-8")
    )
    assert [(record["year"], record["month"]) for record in records] == [
        (2026, 4),
        (2026, 5),
        (2025, 4),
    ]
    snapshot = json.loads(
        (final_output / "after_sales_monthly_snapshot.json").read_text(encoding="utf-8")
    )
    snapshot_records = snapshot["payload"]["records"]
    assert len(snapshot_records) == 1
    assert snapshot_records[0]["year"] == 2026
    assert snapshot_records[0]["month"] == 4


def test_unknown_year_can_be_confirmed_without_silent_rewrite(tmp_path: Path) -> None:
    source = tmp_path / "年份未注明.xlsx"
    _make_workbook(source, complaint_date="4月10日")
    payload = _job(
        [source],
        tmp_path / "unknown-draft",
        year=2026,
        month=4,
    )
    draft = _bind_framework_ai(tmp_path, payload, "unknown-year")
    fields = {prompt["field"] for prompt in draft["confirmations"]}
    assert TASK_PERIOD_SCOPE_FIELD in fields
    assert "complaint_date" in fields

    confirmation_path = _confirmation_file(tmp_path / "unknown-confirm.json", draft)
    final_output = tmp_path / "unknown-final"
    final = _run(
        tmp_path,
        {
            **payload,
            "job_id": "unknown-final",
            "phase": "finalize",
            "output_dir": str(final_output.resolve()),
            "parent_job_id": "period-draft",
            "confirmation_file": str(confirmation_path.resolve()),
        },
        "unknown-final",
    )

    assert final["status"] == "success"
    records = json.loads(
        (final_output / "after_sales_records.json").read_text(encoding="utf-8")
    )
    assert records[0]["complaint_date"] == "2026-04-10"
    assert records[0]["year"] == 2026
    assert records[0]["month"] == 4


def test_unknown_year_left_unresolved_fails_before_formal_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "年份仍未注明.xlsx"
    _make_workbook(source, complaint_date="4月10日")
    payload = _job(
        [source],
        tmp_path / "unresolved-draft",
        year=2026,
        month=4,
    )
    draft = _bind_framework_ai(tmp_path, payload, "unresolved")
    prompts = draft["confirmations"]
    assert isinstance(prompts, list)
    confirmation_path = tmp_path / "unresolved-confirm.json"
    confirmation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "period-draft",
                "answers": [
                    {
                        "confirmation_id": prompt["confirmation_id"],
                        "value": (
                            "4月10日"
                            if prompt["field"] == "complaint_date"
                            else _confirmation_value(prompt)
                        ),
                    }
                    for prompt in prompts
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "unresolved-final"
    final = _run(
        tmp_path,
        {
            **payload,
            "job_id": "unresolved-final",
            "phase": "finalize",
            "output_dir": str(final_output.resolve()),
            "parent_job_id": "period-draft",
            "confirmation_file": str(confirmation_path.resolve()),
        },
        "unresolved-final",
    )

    assert final["status"] == "failed"
    assert any(TASK_PERIOD_UNRESOLVED_CODE in error for error in final["errors"])
    assert final["outputs"] == []
    assert not (final_output / "after_sales_monthly_snapshot.json").exists()
    assert {path.name for path in final_output.iterdir()} == {"result.json"}

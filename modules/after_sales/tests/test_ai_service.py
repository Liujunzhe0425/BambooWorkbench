from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent.ai_service import (  # noqa: E402
    MAX_PAYLOAD_BYTES,
    apply_ai_service_outcome,
    build_ai_service_requests,
    needs_ai_assistance,
    read_ai_service_responses,
)
from after_sales_agent.cli import _create_sample_workbook, run_job  # noqa: E402


def _record(index: int, text: str = "") -> dict[str, object]:
    return {
        "input_index": index,
        "case_id": f"ai-root-{index}",
        "file_sha256": f"{index:064x}",
        "source_file": f"脱敏样表{index}.xlsx",
        "included_in_summary": True,
        "brand": "桃花江",
        "product": "户外竹地板",
        "feedback": text or "地板开裂并出现色差",
        "application": text or "申请补发并承担运费",
        "investigation": text or "调查确认开片指令错误导致尺寸不符",
        "solution": text or "最终补发，材料费1200元、运费300元",
        "responsibility": "责任工厂：二厂",
        "enterprise_cost_amount": 1500.0,
        "enterprise_cost_status": "exact",
        "enterprise_cost_evidence": "材料费1200元、运费300元",
        "issue_types": ["加工"],
        "primary_issue_type": "加工",
        "issue_reason_summary": "开片指令错误导致尺寸不符",
        "issue_confidence": 0.8,
        "issue_analysis_source": "rules",
        "selected_solution": "最终补发",
        "responsible_factory": "二厂",
        "resolution_status": "处理中",
        "closed": False,
        "analysis_status": "离线规则分析完成",
    }


def _analysis(candidate: dict[str, object]) -> dict[str, object]:
    evidence = candidate["rule_evidence"]
    assert isinstance(evidence, list) and evidence
    return {
        "candidate_id": candidate["candidate_id"],
        "issue_types": ["加工"],
        "primary_issue_type": "加工",
        "reason_summary": "开片指令错误导致尺寸不符",
        "evidence_refs": [evidence[0]["evidence_id"]],
        "review_suggestion": "请核对开片指令与现场尺寸记录",
        "confidence": 0.93,
    }


def _write_response(
    path: Path,
    requests: list[dict[str, object]],
    *,
    status: str = "ok",
    task_id: str = "ai-root",
    mutate: object | None = None,
) -> None:
    responses = []
    for request in requests:
        payload = request["payload"]
        assert isinstance(payload, dict)
        analyses = [_analysis(candidate) for candidate in payload["candidates"]]
        if callable(mutate):
            mutate(analyses)
        responses.append(
            {
                "request_id": request["request_id"],
                "service": "ai",
                "status": status,
                "text": (
                    json.dumps(
                        {
                            "schema_version": "1.0",
                            "batch_id": payload["batch_id"],
                            "analyses": analyses,
                        },
                        ensure_ascii=False,
                    )
                    if status == "ok"
                    else None
                ),
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task_id": task_id,
                "module_id": "after_sales",
                "responses": responses,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _job(source: Path, output: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "ai-root",
        "module_id": "after_sales",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(source.resolve())],
        "output_dir": str(output.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    payload.update(overrides)
    return payload


def test_build_requests_covers_100_files_once_with_bounded_sanitized_payloads() -> None:
    private_text = (
        "客户：张三，联系13800138000，邮箱someone@example.com，"
        "路径D:\\private\\customer，珠海某某有限公司；" + "调查结论。" * 300
    )
    records = [_record(index, private_text) for index in range(1, 101)]

    requests = build_ai_service_requests(root_job_id="ai-root", records=records)

    assert len(requests) > 1
    candidates = [
        candidate for request in requests for candidate in request["payload"]["candidates"]
    ]
    assert len(candidates) == len({item["candidate_id"] for item in candidates}) == 100
    for request in requests:
        encoded = json.dumps(
            request["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        outbound = encoded.decode("utf-8")
        assert len(encoded) <= MAX_PAYLOAD_BYTES
        assert "13800138000" not in outbound
        assert "someone@example.com" not in outbound
        assert "D:\\private" not in outbound
        assert "张三" not in outbound
        assert "珠海某某有限公司" not in outbound
        assert "source_file" not in outbound
        assert "customer" not in outbound
        assert request["requires_user_consent"] is True
        assert request["response_format"] == "json_object"


def test_clear_high_confidence_rule_result_does_not_request_ai() -> None:
    record = _record(1)
    record["issue_confidence"] = 0.98
    assert needs_ai_assistance(record) is False
    assert build_ai_service_requests(root_job_id="ai-root", records=[record]) == []
    assert record["ai_service_status"] == "无需AI辅助"


def test_valid_response_changes_only_low_risk_analysis_fields(tmp_path: Path) -> None:
    record = _record(1)
    original_high_risk = {
        key: record[key]
        for key in (
            "brand",
            "enterprise_cost_amount",
            "responsible_factory",
            "resolution_status",
            "closed",
        )
    }
    requests = build_ai_service_requests(root_job_id="ai-root", records=[record])
    response_path = tmp_path / "service-response.json"
    _write_response(response_path, requests)

    outcome = read_ai_service_responses(
        response_path, root_job_id="ai-root", requests=requests
    )
    apply_ai_service_outcome([record], outcome)

    assert not outcome.warnings
    assert record["issue_reason_summary"] == "开片指令错误导致尺寸不符"
    assert record["ai_review_suggestion"] == "请核对开片指令与现场尺寸记录"
    assert record["analysis_status"] == "AI辅助分析完成（待人工复核）"
    assert all(record[key] == value for key, value in original_high_risk.items())


def test_response_with_fee_or_responsibility_field_is_rejected(tmp_path: Path) -> None:
    record = _record(1)
    requests = build_ai_service_requests(root_job_id="ai-root", records=[record])
    response_path = tmp_path / "service-response.json"

    def add_forbidden_field(analyses: list[dict[str, object]]) -> None:
        analyses[0]["cost_amount"] = 1
        analyses[0]["responsible_factory"] = "一厂"

    _write_response(response_path, requests, mutate=add_forbidden_field)
    outcome = read_ai_service_responses(
        response_path, root_job_id="ai-root", requests=requests
    )
    apply_ai_service_outcome([record], outcome)

    assert outcome.warnings
    assert not outcome.analyses
    assert record["enterprise_cost_amount"] == 1500
    assert record["responsible_factory"] == "二厂"
    assert "降级" in record["analysis_status"]


def test_denial_timeout_and_missing_response_all_degrade_without_dropping_case(
    tmp_path: Path,
) -> None:
    for status in ("denied", "timeout", "rate_limited", "unavailable"):
        record = _record(1)
        requests = build_ai_service_requests(root_job_id="ai-root", records=[record])
        response_path = tmp_path / f"{status}.json"
        _write_response(response_path, requests, status=status)
        outcome = read_ai_service_responses(
            response_path, root_job_id="ai-root", requests=requests
        )
        apply_ai_service_outcome([record], outcome)
        assert outcome.warnings
        assert record["issue_types"] == ["加工"]
        assert "降级" in record["analysis_status"]

    missing_record = _record(2)
    missing_requests = build_ai_service_requests(
        root_job_id="ai-root", records=[missing_record]
    )
    missing = read_ai_service_responses(
        tmp_path / "not-created.json",
        root_job_id="ai-root",
        requests=missing_requests,
    )
    apply_ai_service_outcome([missing_record], missing)
    assert missing.warnings
    assert "降级" in missing_record["analysis_status"]


def test_unknown_evidence_reference_is_rejected(tmp_path: Path) -> None:
    record = _record(1)
    requests = build_ai_service_requests(root_job_id="ai-root", records=[record])
    response_path = tmp_path / "unknown-evidence.json"

    def replace_evidence(analyses: list[dict[str, object]]) -> None:
        analyses[0]["evidence_refs"] = ["not-in-request"]

    _write_response(response_path, requests, mutate=replace_evidence)
    outcome = read_ai_service_responses(
        response_path, root_job_id="ai-root", requests=requests
    )
    apply_ai_service_outcome([record], outcome)

    assert not outcome.analyses
    assert outcome.warnings
    assert "降级" in record["analysis_status"]


def test_desktop_cli_uses_shared_service_and_human_review_overrides_ai(
    tmp_path: Path,
) -> None:
    source = tmp_path / "脱敏售后样表.xlsx"
    _create_sample_workbook(
        source,
        customer="脱敏客户",
        brand_text="桃花江户外竹地板",
        date_text="2026-05-10",
        feedback="产品尺寸不符并有色差",
        solution="已安排补发，企业售后成本1500元，由二厂承担，尚未完成。",
    )
    draft_output = tmp_path / "output-draft"
    draft_job = _job(source, draft_output)
    draft_job_path = tmp_path / "draft-job.json"
    draft_job_path.write_text(json.dumps(draft_job, ensure_ascii=False), encoding="utf-8")

    with patch("urllib.request.urlopen") as direct_gateway:
        assert (
            run_job(
                draft_job_path,
                {"api": {"api_key": "must-never-be-read"}, "progress_callback": None},
            )
            == 0
        )
    direct_gateway.assert_not_called()
    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    assert draft["service_requests"]
    assert {item["field"] for item in draft["confirmations"]} >= {
        "售后费用",
        "责任工厂",
        "投诉类型",
    }

    answers = []
    for item in draft["confirmations"]:
        value = item.get("suggested_value")
        if item["field"] == "售后费用":
            value = 3200
        elif item["field"] == "责任工厂":
            value = "成品厂"
        elif item["field"] == "投诉类型":
            value = "性能"
        answers.append({"confirmation_id": item["confirmation_id"], "value": value})
    confirmation_path = tmp_path / "confirmation.json"
    confirmation_path.write_text(
        json.dumps(
            {"schema_version": "1.0", "job_id": "ai-root", "answers": answers},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service_path = tmp_path / "service-response.json"
    _write_response(service_path, draft["service_requests"])
    final_output = tmp_path / "output-final"
    final_job = _job(
        source,
        final_output,
        job_id="ai-final",
        phase="finalize",
        parent_job_id="ai-root",
        confirmation_file=str(confirmation_path.resolve()),
        service_response_file=str(service_path.resolve()),
        ai_enabled=True,
    )
    final_job_path = tmp_path / "final-job.json"
    final_job_path.write_text(json.dumps(final_job, ensure_ascii=False), encoding="utf-8")
    assert run_job(final_job_path) == 0

    final = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    records = json.loads((final_output / "after_sales_records.json").read_text(encoding="utf-8"))
    record = records[0]
    assert final["status"] == "success"
    assert final["service_requests"] == []
    assert record["issue_reason_summary"] == "开片指令错误导致尺寸不符"
    assert record["primary_issue_type"] == "性能"
    assert record["enterprise_cost_amount"] == 3200
    assert record["responsible_factory"] == "成品厂"
    assert record["resolution_status"] != "已解决"
    assert record["analysis_status"] == "AI辅助分析完成（已人工复核）"
    report = (final_output / "after_sales_analysis.md").read_text(encoding="utf-8")
    assert "AI辅助分析：1 件" in report
    assert "售后费用、责任工厂" in report


def test_desktop_entry_has_no_credential_or_direct_gateway_dependency() -> None:
    cli_source = (MODULE_ROOT / "src" / "after_sales_agent" / "cli.py").read_text(
        encoding="utf-8"
    )
    extractor_source = (
        MODULE_ROOT / "src" / "after_sales_agent" / "extractor.py"
    ).read_text(encoding="utf-8")
    requirements = (MODULE_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "module_ai_config" not in cli_source
    assert "deepseek_gateway" not in cli_source
    assert "analyze_issue_with_api" not in cli_source
    assert "deepseek_gateway" not in extractor_source
    assert "analyze_issue_with_api" not in extractor_source
    assert "keyring" not in requirements

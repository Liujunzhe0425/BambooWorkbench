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
    read_ai_service_responses,
)
from after_sales_agent.cli import _create_sample_workbook, run_job  # noqa: E402


def _record(index: int, text: str = "") -> dict[str, object]:
    return {
        "case_id": f"ai-root-{index}",
        "included_in_summary": True,
        "brand": "未知",
        "product": "户外竹地板",
        "feedback": text or "地板开裂并出现色差",
        "application": text or "申请补发并承担运费",
        "investigation": text or "调查确认开片指令错误导致尺寸不符",
        "solution": text or "最终补发，材料费1200元、运费300元",
        "responsibility": "责任工厂：二厂",
        "enterprise_cost_amount": 1500.0,
        "enterprise_cost_evidence": "材料费1200元、运费300元",
        "issue_types": ["加工"],
        "primary_issue_type": "加工",
        "issue_confidence": 0.8,
        "selected_solution": "最终补发",
        "resolution_status": "处理中",
        "closed": False,
    }


def _analysis(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "brand_name": "桃花江",
        "brand_reason": "产品原文出现桃花江",
        "issue_types": ["加工"],
        "primary_issue_type": "加工",
        "reason_summary": "开片指令错误导致尺寸不符",
        "evidence": ["开片指令错误", "尺寸不符"],
        "responsible_factory": "二厂",
        "responsible_factory_reason": "责任工厂：二厂",
        "selected_solution": "补发产品",
        "cost_items": [
            {"name": "材料费", "amount": 1200, "included": True, "evidence": "材料费1200元"},
            {"name": "运费", "amount": 300, "included": True, "evidence": "运费300元"},
        ],
        "cost_amount": 1500,
        "cost_included": True,
        "cost_reason": "材料费1200元、运费300元",
        "resolution_status": "处理中",
        "resolution_reason": "方案已确定但尚未写明完成",
        "confidence": 0.93,
        "needs_manual_review": True,
    }


def _write_response(
    path: Path,
    requests: list[dict[str, object]],
    *,
    omit_last_case: bool = False,
    task_id: str = "ai-root",
) -> None:
    responses = []
    for request in requests:
        request_payload = request["payload"]
        assert isinstance(request_payload, dict)
        cases = request_payload["cases"]
        assert isinstance(cases, list)
        analyses = [_analysis(str(item["case_id"])) for item in cases]
        if omit_last_case and analyses:
            analyses.pop()
        responses.append(
            {
                "request_id": request["request_id"],
                "service": "ai",
                "status": "ok",
                "text": json.dumps(
                    {
                        "schema_version": "1.0",
                        "batch_id": request_payload["batch_id"],
                        "analyses": analyses,
                    },
                    ensure_ascii=False,
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


def test_build_requests_covers_100_files_once_with_bounded_payloads() -> None:
    private_text = (
        "联系13800138000，邮箱someone@example.com，路径D:\\private\\customer；"
        + "售后调查结论和方案。" * 400
    )
    records = [_record(index, private_text) for index in range(1, 101)]

    requests = build_ai_service_requests(root_job_id="ai-root", records=records)

    assert len(requests) > 1
    case_ids = [case["case_id"] for request in requests for case in request["payload"]["cases"]]
    assert case_ids == [f"ai-root-{index}" for index in range(1, 101)]
    assert len(case_ids) == len(set(case_ids)) == 100
    for request in requests:
        encoded = json.dumps(
            request["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        assert len(encoded) <= MAX_PAYLOAD_BYTES
        outbound = encoded.decode("utf-8")
        assert "13800138000" not in outbound
        assert "someone@example.com" not in outbound
        assert "D:\\private" not in outbound
        assert request["requires_user_consent"] is True


def test_valid_response_is_applied_but_does_not_replace_deterministic_fee(tmp_path: Path) -> None:
    records = [_record(1)]
    records[0]["enterprise_cost_amount"] = 1600.0
    requests = build_ai_service_requests(root_job_id="ai-root", records=records)
    response_path = tmp_path / "service-response.json"
    _write_response(response_path, requests)

    outcome = read_ai_service_responses(
        response_path,
        root_job_id="ai-root",
        requests=requests,
    )
    apply_ai_service_outcome(records, outcome)

    assert not outcome.errors
    assert records[0]["ai_service_status"] == "智能分析完成"
    assert records[0]["brand"] == "桃花江"
    assert records[0]["issue_reason_summary"] == "开片指令错误导致尺寸不符"
    assert records[0]["responsible_factory_ai_candidate"] == "二厂"
    assert records[0]["api_cost_candidate"] == 1500.0
    assert records[0]["enterprise_cost_amount"] == 1600.0
    assert records[0]["needs_review"] is True


def test_incomplete_response_rejects_the_whole_chunk_and_keeps_every_record(tmp_path: Path) -> None:
    records = [_record(1), _record(2)]
    requests = build_ai_service_requests(root_job_id="ai-root", records=records)
    response_path = tmp_path / "service-response.json"
    _write_response(response_path, requests, omit_last_case=True)

    outcome = read_ai_service_responses(
        response_path,
        root_job_id="ai-root",
        requests=requests,
    )
    apply_ai_service_outcome(records, outcome)

    assert outcome.errors
    assert outcome.analyses == {}
    assert len(records) == 2
    assert all(record["ai_service_status"] == "返回无效" for record in records)
    assert all(record["brand"] == "未知" for record in records)
    assert all(record["needs_review"] is True for record in records)


def test_cli_uses_module_ai_before_review_without_refusal_and_reuses_draft_snapshot(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.xlsx"
    _create_sample_workbook(
        source,
        customer="脱敏客户",
        brand_text="桃花江户外竹地板",
        date_text="2026-05-10",
        feedback="产品尺寸不符",
        solution="补发产品，费用以人工复核为准，正在处理中。",
    )
    draft_output = tmp_path / "output-draft"
    draft_job = {
        "schema_version": "1.0",
        "job_id": "ai-draft",
        "module_id": "after_sales",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(source.resolve())],
        "output_dir": str(draft_output.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    draft_job_path = tmp_path / "draft-job.json"
    draft_job_path.write_text(json.dumps(draft_job, ensure_ascii=False), encoding="utf-8")
    calls: list[str] = []

    def fake_analysis(*_args, **_kwargs):
        calls.append("analysis")
        return _analysis("ai-draft-1")

    with patch(
        "after_sales_agent.extractor.analyze_issue_with_api",
        side_effect=fake_analysis,
    ):
        assert (
            run_job(
                draft_job_path,
                {
                    "api": {
                        "provider": "deepseek",
                        "api_key": "sk-test",
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-v4-flash",
                    }
                },
            )
            == 0
        )
    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    assert draft["service_requests"] == []
    assert calls == ["analysis"]
    assert {item["field"] for item in draft["confirmations"]} >= {
        "售后费用",
        "责任工厂",
        "投诉类型",
    }
    prompts = {item["field"]: item for item in draft["confirmations"]}
    assert prompts["售后费用"]["suggested_value"] == 1500
    assert prompts["责任工厂"]["suggested_value"] == "二厂"
    assert all("拒绝" not in json.dumps(item, ensure_ascii=False) for item in draft["confirmations"])

    confirmation_path = tmp_path / "confirmation.json"
    confirmation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "ai-draft",
                "answers": [
                    {
                        "confirmation_id": item["confirmation_id"],
                        "value": item.get("suggested_value"),
                    }
                    for item in draft["confirmations"]
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "output-final"
    final_job = {
        **draft_job,
        "job_id": "ai-final",
        "phase": "finalize",
        "output_dir": str(final_output.resolve()),
        "parent_job_id": "ai-draft",
        "confirmation_file": str(confirmation_path.resolve()),
        "service_response_file": None,
    }
    final_job_path = tmp_path / "final-job.json"
    final_job_path.write_text(json.dumps(final_job, ensure_ascii=False), encoding="utf-8")
    assert run_job(final_job_path) == 0
    final = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    records = json.loads((final_output / "after_sales_records.json").read_text(encoding="utf-8"))

    assert final["service_requests"] == []
    assert calls == ["analysis"]
    assert records[0]["issue_analysis_source"] == "api"
    assert records[0]["issue_reason_summary"] == "开片指令错误导致尺寸不符"
    assert records[0]["responsible_factory"] == "二厂"

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def analysis_for_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(case["case_id"]),
        "brand_name": "桃花江",
        "brand_reason": "产品描述中出现桃花江",
        "issue_types": ["加工"],
        "primary_issue_type": "加工",
        "reason_summary": "开片指令错误导致尺寸不符",
        "evidence": ["开片指令错误", "尺寸不符"],
        "responsible_factory": "二厂",
        "responsible_factory_reason": "调查记录指向二厂",
        "selected_solution": "补发产品",
        "cost_items": [
            {
                "name": "材料费",
                "amount": 1200,
                "included": True,
                "evidence": "材料费1200元",
            },
            {
                "name": "运费",
                "amount": 300,
                "included": True,
                "evidence": "运费300元",
            },
        ],
        "cost_amount": 1500,
        "cost_included": True,
        "cost_reason": "材料费1200元、运费300元",
        "resolution_status": "处理中",
        "resolution_reason": "方案已确定但尚未写明完成",
        "confidence": 0.93,
        "needs_manual_review": True,
    }


def write_service_response(
    path: Path,
    requests: list[dict[str, Any]],
    *,
    task_id: str,
    status: str = "error",
    invalid_text: bool = False,
) -> Path:
    responses: list[dict[str, Any]] = []
    for request in requests:
        response: dict[str, Any] = {
            "request_id": request["request_id"],
            "service": "ai",
            "status": status,
            "text": None,
        }
        if status == "ok":
            payload = request["payload"]
            response["text"] = (
                "not-json"
                if invalid_text
                else json.dumps(
                    {
                        "schema_version": "1.0",
                        "batch_id": payload["batch_id"],
                        "analyses": [
                            analysis_for_case(case) for case in payload["cases"]
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        responses.append(response)
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
    return path

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from after_sales_agent.llm_analyzer import normalize_analysis

AI_RESPONSE_SCHEMA_VERSION = "1.0"
ISSUE_CATEGORIES = ("性能", "外观", "加工", "其他")
MAX_PAYLOAD_BYTES = 65_536
MAX_CASES_PER_REQUEST = 10
MAX_SECTION_CHARS = 2_000

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1\d{10}(?!\d)")
_LOCAL_PATH_RE = re.compile(r"(?i)(?:[A-Z]:[\\/]|\\\\[^\\\s]+\\)[^\r\n；。]*")


class AIServiceResponseError(ValueError):
    """The shared AI service response cannot be safely applied to a case."""


@dataclass(frozen=True, slots=True)
class AIServiceOutcome:
    analyses: dict[str, dict[str, Any]]
    errors: tuple[str, ...]
    case_status: dict[str, str]


def build_ai_service_requests(
    *,
    root_job_id: str,
    records: list[dict[str, Any]],
    max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    max_cases_per_request: int = MAX_CASES_PER_REQUEST,
) -> list[dict[str, Any]]:
    """Build bounded, deterministic framework AI requests without reading an API key."""

    cases = [_case_payload(record) for record in records if record.get("included_in_summary")]
    if not cases:
        return []

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for case in cases:
        proposed = [*current, case]
        if current and (
            len(proposed) > max_cases_per_request
            or _payload_size(_request_payload("pending", proposed)) > max_payload_bytes
        ):
            chunks.append(current)
            current = [case]
        else:
            current = proposed
    if current:
        chunks.append(current)

    requests: list[dict[str, Any]] = []
    total = len(cases)
    first = 1
    for chunk_index, chunk in enumerate(chunks, start=1):
        last = first + len(chunk) - 1
        batch_id = _batch_id(root_job_id, chunk_index, chunk)
        payload = _request_payload(batch_id, chunk)
        requests.append(
            {
                "request_id": f"after-sales-ai-{batch_id}",
                "service": "ai",
                "scope": None,
                "purpose": f"智能分析第 {first}-{last}/{total} 份售后Excel",
                "payload": payload,
                "requires_user_consent": True,
            }
        )
        first = last + 1
    return requests


def read_ai_service_responses(
    path: Path | None,
    *,
    root_job_id: str,
    requests: list[dict[str, Any]],
) -> AIServiceOutcome:
    """Read, bind and validate all task-local AI responses without dropping a case."""

    expected = {str(item["request_id"]): item for item in requests}
    expected_case_ids = {
        str(case["case_id"]) for request in requests for case in request["payload"].get("cases", [])
    }
    statuses = {case_id: "未返回" for case_id in expected_case_ids}
    if not expected:
        return AIServiceOutcome({}, (), statuses)
    if path is None or not path.is_file():
        return AIServiceOutcome(
            {},
            ("AI_SERVICE_RESPONSE_MISSING：未收到统一工作台的AI响应，已使用离线结果。",),
            statuses,
        )

    try:
        envelope = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, AIServiceResponseError):
        return AIServiceOutcome(
            {},
            ("AI_SERVICE_RESPONSE_INVALID：AI响应文件不是有效JSON，已使用离线结果。",),
            statuses,
        )
    if not isinstance(envelope, dict):
        return AIServiceOutcome(
            {},
            ("AI_SERVICE_RESPONSE_INVALID：AI响应文件结构无效，已使用离线结果。",),
            statuses,
        )
    if (
        envelope.get("schema_version") != "1.0"
        or envelope.get("task_id") != root_job_id
        or envelope.get("module_id") != "after_sales"
        or not isinstance(envelope.get("responses"), list)
    ):
        return AIServiceOutcome(
            {},
            ("AI_SERVICE_RESPONSE_MISMATCH：AI响应与当前售后任务不匹配，已使用离线结果。",),
            statuses,
        )

    analyses: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    seen_requests: set[str] = set()
    for raw_response in envelope["responses"]:
        if not isinstance(raw_response, dict):
            errors.append("AI_SERVICE_RESPONSE_INVALID：存在无效的AI响应项。")
            continue
        request_id = str(raw_response.get("request_id") or "")
        request = expected.get(request_id)
        if request is None or request_id in seen_requests or raw_response.get("service") != "ai":
            errors.append("AI_SERVICE_RESPONSE_MISMATCH：AI响应编号重复或不属于当前任务。")
            continue
        seen_requests.add(request_id)
        case_ids = {str(item["case_id"]) for item in request["payload"]["cases"]}
        status = str(raw_response.get("status") or "error")
        if status != "ok":
            label = {"denied": "用户未授权", "timeout": "请求超时"}.get(status, "服务错误")
            errors.append(f"{request_id}：{label}，对应文件已使用离线结果并保留人工复核。")
            for case_id in case_ids:
                statuses[case_id] = label
            continue
        try:
            parsed = _parse_response_text(raw_response.get("text"), request)
        except AIServiceResponseError as exc:
            errors.append(f"{request_id}：AI结构化结果无效（{exc}），已使用离线结果。")
            for case_id in case_ids:
                statuses[case_id] = "返回无效"
            continue
        for case_id, analysis in parsed.items():
            if case_id in analyses:
                errors.append(f"{request_id}：案件 {case_id} 重复返回，已拒绝重复结果。")
                statuses[case_id] = "返回无效"
                analyses.pop(case_id, None)
                continue
            analyses[case_id] = analysis
            statuses[case_id] = "智能分析完成"

    for missing_request in sorted(set(expected) - seen_requests):
        errors.append(f"{missing_request}：AI响应缺失，对应文件已使用离线结果。")
        for case in expected[missing_request]["payload"]["cases"]:
            statuses[str(case["case_id"])] = "未返回"
    return AIServiceOutcome(analyses, tuple(errors), statuses)


def apply_ai_service_outcome(records: list[dict[str, Any]], outcome: AIServiceOutcome) -> None:
    """Apply validated AI suggestions; deterministic amounts and human answers remain final."""

    for record in records:
        case_id = str(record.get("case_id") or "")
        status = outcome.case_status.get(case_id)
        if not status:
            continue
        record["ai_service_status"] = status
        analysis = outcome.analyses.get(case_id)
        if analysis is None:
            record["analysis_note"] = f"AI辅助未完成（{status}），已保留离线结果并等待人工复核"
            record["needs_review"] = True
            continue

        record["api_analysis"] = analysis
        brand = analysis["brand_name"]
        if brand != "未知":
            record["brand"] = brand
            record["brand_confidence"] = analysis["confidence"]
            record["brand_reason"] = analysis["brand_reason"]
            record["brand_evidence"] = analysis["brand_reason"]
        record["issue_types"] = analysis["issue_types"]
        record["primary_issue_type"] = analysis["primary_issue_type"]
        record["issue_reason_summary"] = analysis["reason_summary"]
        record["issue_confidence"] = analysis["confidence"]
        record["issue_evidence"] = {"api": analysis["evidence"]}
        record["issue_analysis_source"] = "api"
        record["selected_solution"] = analysis["selected_solution"] or record.get(
            "selected_solution", ""
        )
        record["responsible_factory_ai_candidate"] = analysis["responsible_factory"]
        record["responsible_factory_ai_reason"] = analysis["responsible_factory_reason"]
        if not record.get("responsibility_reviewed") and analysis["responsible_factory"]:
            record["responsible_factory"] = analysis["responsible_factory"]
        record["api_cost_candidate"] = analysis["cost_amount"]
        record["api_cost_evidence"] = analysis["cost_reason"]
        record["api_cost_items"] = analysis["cost_items"]
        record["resolution_status"] = analysis["resolution_status"]
        record["resolution_reason"] = analysis["resolution_reason"]
        record["resolution_analysis_source"] = "api"
        record["closed"] = analysis["resolution_status"] == "已解决"
        record["case_status"] = (
            "已关闭"
            if record["closed"]
            else ("处理中" if analysis["resolution_status"] == "处理中" else "待确认")
        )
        record["analysis_status"] = "AI智能分析完成"
        record["analysis_note"] = "已使用统一工作台授权的AI服务辅助分析，最终以人工复核为准"
        record["needs_review"] = True


def _case_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(record.get("case_id") or ""),
        "current_brand_candidate": _clean_text(record.get("brand"), 100),
        "product": _clean_text(record.get("product"), 500),
        "feedback": _clean_text(record.get("feedback"), MAX_SECTION_CHARS),
        "application_detail": _clean_text(record.get("application"), MAX_SECTION_CHARS),
        "investigation": _clean_text(record.get("investigation"), MAX_SECTION_CHARS),
        "solution": _clean_text(record.get("solution"), MAX_SECTION_CHARS),
        "responsibility": _clean_text(record.get("responsibility"), MAX_SECTION_CHARS),
        "deterministic_fee_candidate": record.get("enterprise_cost_amount"),
        "deterministic_fee_evidence": _clean_text(record.get("enterprise_cost_evidence"), 1_000),
    }


def _request_payload(batch_id: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": AI_RESPONSE_SCHEMA_VERSION,
        "batch_id": batch_id,
        "instruction": (
            "逐个分析cases中的售后Excel案件。只依据反馈内容、方案申请明细、售后负责人调查情况、"
            "售后解决方案和责任落实，不得编造。品牌不能用客户代替；未知写未知。"
            "主投诉类型只能是性能、外观、加工、其他。费用只能提取最终采用方案的明确金额，"
            "没有明确金额必须为null，不能写0。责任工厂不明确写未知。"
            "根因优先采用调查情况；只有明确完成处理才判为已解决。"
            "返回一个JSON对象，不要Markdown，analyses必须逐一覆盖全部case_id且不得增加案件。"
        ),
        "output_contract": {
            "schema_version": "1.0",
            "batch_id": batch_id,
            "analyses": [
                {
                    "case_id": "原样返回",
                    "brand_name": "产品品牌或未知",
                    "brand_reason": "短证据",
                    "issue_types": ["性能|外观|加工|其他"],
                    "primary_issue_type": "性能|外观|加工|其他",
                    "reason_summary": "具体售后根因或现象并注明根因未写明",
                    "evidence": ["短证据"],
                    "responsible_factory": "责任工厂/部门或未知",
                    "responsible_factory_reason": "短证据",
                    "selected_solution": "最终采用方案",
                    "cost_items": [
                        {
                            "name": "费用名称",
                            "amount": "非负数字或null",
                            "included": True,
                            "evidence": "短证据",
                        }
                    ],
                    "cost_amount": "最终方案明确总费用；非负数字或null",
                    "cost_included": True,
                    "cost_reason": "短证据",
                    "resolution_status": "已解决|处理中|未解决",
                    "resolution_reason": "短证据",
                    "confidence": "0到1数字",
                    "needs_manual_review": True,
                }
            ],
        },
        "cases": cases,
    }


def _parse_response_text(text: Any, request: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        raise AIServiceResponseError("响应文本为空")
    cleaned = _CODE_FENCE_RE.sub("", text.strip()).strip()
    try:
        payload = json.loads(cleaned, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, AIServiceResponseError) as exc:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match is None:
            raise AIServiceResponseError("不是JSON对象") from exc
        try:
            payload = json.loads(match.group(0), object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, AIServiceResponseError) as nested:
            raise AIServiceResponseError("不是有效JSON") from nested
    if not isinstance(payload, dict):
        raise AIServiceResponseError("顶层不是对象")
    batch_id = str(request["payload"]["batch_id"])
    if payload.get("schema_version") != AI_RESPONSE_SCHEMA_VERSION:
        raise AIServiceResponseError("schema_version不匹配")
    if payload.get("batch_id") != batch_id:
        raise AIServiceResponseError("batch_id不匹配")
    raw_analyses = payload.get("analyses")
    if not isinstance(raw_analyses, list):
        raise AIServiceResponseError("缺少analyses数组")

    expected = {str(item["case_id"]) for item in request["payload"]["cases"]}
    parsed: dict[str, dict[str, Any]] = {}
    for raw in raw_analyses:
        analysis = _validate_analysis(raw)
        case_id = analysis.pop("case_id")
        if case_id not in expected or case_id in parsed:
            raise AIServiceResponseError("case_id未知或重复")
        parsed[case_id] = analysis
    if set(parsed) != expected:
        raise AIServiceResponseError("没有逐一覆盖全部输入文件")
    return parsed


def _validate_analysis(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise AIServiceResponseError("案件分析不是对象")
    case_id = str(raw.get("case_id") or "").strip()
    if not case_id:
        raise AIServiceResponseError("case_id为空")
    normalized = normalize_analysis(raw, list(ISSUE_CATEGORIES))
    raw_types = raw.get("issue_types")
    if not isinstance(raw_types, list) or not raw_types:
        raise AIServiceResponseError("issue_types无效")
    if any(str(item) not in ISSUE_CATEGORIES for item in raw_types):
        raise AIServiceResponseError("issue_types超出允许范围")
    if str(raw.get("primary_issue_type")) not in ISSUE_CATEGORIES:
        raise AIServiceResponseError("primary_issue_type无效")
    if normalized["primary_issue_type"] not in normalized["issue_types"]:
        raise AIServiceResponseError("主投诉类型不在投诉类型列表中")
    confidence = _number(raw.get("confidence"), "confidence", allow_none=False)
    if confidence is None or not 0 <= confidence <= 1:
        raise AIServiceResponseError("confidence必须在0到1之间")
    cost_amount = _number(raw.get("cost_amount"), "cost_amount", allow_none=True)
    cost_items = _validate_cost_items(raw.get("cost_items"))
    resolution_status = str(raw.get("resolution_status") or "").strip()
    if resolution_status not in {"已解决", "处理中", "未解决"}:
        raise AIServiceResponseError("resolution_status无效")
    evidence = normalized["evidence"]
    if not normalized["reason_summary"] or not evidence:
        raise AIServiceResponseError("原因或证据为空")
    normalized.update(
        {
            "case_id": case_id,
            "responsible_factory": _short(raw.get("responsible_factory"), 100) or "未知",
            "responsible_factory_reason": _short(raw.get("responsible_factory_reason"), 500),
            "cost_items": cost_items,
            "cost_amount": cost_amount,
            "cost_reason": _short(raw.get("cost_reason"), 1_000),
            "confidence": confidence,
            "resolution_status": resolution_status,
            "resolution_reason": _short(raw.get("resolution_reason"), 1_000),
        }
    )
    return normalized


def _validate_cost_items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 30:
        raise AIServiceResponseError("cost_items无效")
    items: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise AIServiceResponseError("费用项不是对象")
        amount = _number(raw.get("amount"), "cost_items.amount", allow_none=True)
        included = raw.get("included")
        if not isinstance(included, bool):
            raise AIServiceResponseError("cost_items.included必须是布尔值")
        items.append(
            {
                "name": _short(raw.get("name"), 100) or "售后费用",
                "amount": amount,
                "included": included,
                "evidence": _short(raw.get("evidence"), 500),
            }
        )
    return items


def _number(value: Any, field: str, *, allow_none: bool) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise AIServiceResponseError(f"{field}不是数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AIServiceResponseError(f"{field}不是数字") from exc
    if not math.isfinite(number) or number < 0:
        raise AIServiceResponseError(f"{field}必须是非负有限数字")
    return round(number, 2)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AIServiceResponseError(f"JSON字段重复：{key}")
        result[key] = value
    return result


def _batch_id(root_job_id: str, index: int, cases: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        {"root_job_id": root_job_id, "index": index, "cases": cases},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _payload_size(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    text = _EMAIL_RE.sub("[邮箱已脱敏]", text)
    text = _PHONE_RE.sub("[手机号已脱敏]", text)
    text = _LOCAL_PATH_RE.sub("[本地路径已脱敏]", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _short(value: Any, limit: int) -> str:
    return _clean_text(value, limit)

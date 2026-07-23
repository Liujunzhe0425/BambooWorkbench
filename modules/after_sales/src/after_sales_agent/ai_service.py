from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AI_RESPONSE_SCHEMA_VERSION = "1.0"
ISSUE_CATEGORIES = ("性能", "外观", "加工", "其他")
MAX_PAYLOAD_BYTES = 65_536
MAX_CASES_PER_REQUEST = 10
MAX_SUMMARY_CHARS = 1_200

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1\d{10}(?!\d)")
_LOCAL_PATH_RE = re.compile(r"(?i)(?:[A-Z]:[\\/]|\\\\[^\\\s]+\\)[^\r\n；。]*")
_COMPANY_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9（）()·]{2,50}(?:有限责任公司|有限公司)")
_IDENTITY_LABEL_RE = re.compile(
    r"(?:客户(?:姓名)?|联系人|联系电话|手机|地址|项目名称)\s*[:：]\s*"
    r"[^，,；;。\r\n]{1,80}"
)
_ALLOWED_ANALYSIS_FIELDS = {
    "candidate_id",
    "issue_types",
    "primary_issue_type",
    "reason_summary",
    "evidence_refs",
    "review_suggestion",
    "confidence",
}


class AIServiceResponseError(ValueError):
    """The shared AI response cannot be safely bound to an after-sales case."""


@dataclass(frozen=True, slots=True)
class AIServiceOutcome:
    analyses: dict[str, dict[str, Any]]
    warnings: tuple[str, ...]
    candidate_status: dict[str, str]


def needs_ai_assistance(record: dict[str, Any]) -> bool:
    """Return whether a deterministic result has a real semantic-review need."""

    if not record.get("included_in_summary"):
        return False
    issue_types = _normalized_issue_types(record.get("issue_types"))
    primary = str(record.get("primary_issue_type") or "").strip()
    reason = str(record.get("issue_reason_summary") or "").strip()
    try:
        confidence = float(record.get("issue_confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return bool(
        not issue_types
        or primary not in ISSUE_CATEGORIES
        or "其他" in issue_types
        or len(issue_types) > 1
        or confidence < 0.9
        or not reason
        or "根因未写明" in reason
        or "无法确认" in reason
    )


def build_ai_service_requests(
    *,
    root_job_id: str,
    records: list[dict[str, Any]],
    max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    max_cases_per_request: int = MAX_CASES_PER_REQUEST,
) -> list[dict[str, Any]]:
    """Build bounded shared-service requests without reading credentials or networking."""

    candidates: list[dict[str, Any]] = []
    for record in records:
        if not needs_ai_assistance(record):
            record["ai_service_status"] = "无需AI辅助"
            continue
        candidate = _candidate_payload(record)
        record["ai_candidate_id"] = candidate["candidate_id"]
        record["ai_service_status"] = "等待用户授权"
        candidates.append(candidate)
    if not candidates:
        return []

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for candidate in candidates:
        proposed = [*current, candidate]
        pending_payload = _request_payload("pending", proposed)
        if current and (
            len(proposed) > max_cases_per_request
            or _payload_size(pending_payload) > max_payload_bytes
        ):
            chunks.append(current)
            current = [candidate]
        else:
            current = proposed
    if current:
        chunks.append(current)

    requests: list[dict[str, Any]] = []
    first = 1
    total = len(candidates)
    for chunk_index, chunk in enumerate(chunks, start=1):
        last = first + len(chunk) - 1
        batch_id = _batch_id(root_job_id, chunk_index, chunk)
        payload = _request_payload(batch_id, chunk)
        if _payload_size(payload) > max_payload_bytes:
            raise ValueError("单个脱敏售后候选超过统一AI服务的载荷上限")
        requests.append(
            {
                "request_id": f"after-sales-ai-{batch_id}",
                "service": "ai",
                "scope": None,
                "purpose": f"辅助复核第 {first}-{last}/{total} 份售后案件的问题类型与原因",
                "payload": payload,
                "requires_user_consent": True,
                "response_format": "json_object",
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
    """Read and validate task-local responses; every failure degrades to offline rules."""

    expected = {str(item["request_id"]): item for item in requests}
    expected_candidates = {
        str(candidate["candidate_id"])
        for request in requests
        for candidate in request["payload"].get("candidates", [])
    }
    statuses = {candidate_id: "未返回，已降级" for candidate_id in expected_candidates}
    if not expected:
        return AIServiceOutcome({}, (), statuses)
    if path is None or not path.is_file():
        return AIServiceOutcome(
            {},
            ("未收到统一AI服务响应，相关案件已降级为离线规则分析。",),
            statuses,
        )

    try:
        envelope = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, AIServiceResponseError):
        return AIServiceOutcome(
            {},
            ("统一AI服务响应文件无效，相关案件已降级为离线规则分析。",),
            statuses,
        )
    if (
        not isinstance(envelope, dict)
        or envelope.get("schema_version") != "1.0"
        or envelope.get("task_id") != root_job_id
        or envelope.get("module_id") != "after_sales"
        or not isinstance(envelope.get("responses"), list)
    ):
        return AIServiceOutcome(
            {},
            ("统一AI服务响应与当前售后任务不匹配，相关案件已降级。",),
            statuses,
        )

    analyses: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    seen_requests: set[str] = set()
    for raw_response in envelope["responses"]:
        if not isinstance(raw_response, dict):
            warnings.append("存在无效的AI响应项，已忽略并降级。")
            continue
        request_id = str(raw_response.get("request_id") or "")
        request = expected.get(request_id)
        if (
            request is None
            or request_id in seen_requests
            or raw_response.get("service") != "ai"
        ):
            warnings.append("存在重复或不属于当前任务的AI响应，已忽略。")
            continue
        seen_requests.add(request_id)
        candidate_ids = {
            str(item["candidate_id"]) for item in request["payload"]["candidates"]
        }
        status = str(raw_response.get("status") or "error")
        if status != "ok":
            label = {
                "denied": "用户未授权",
                "timeout": "服务超时",
                "rate_limited": "服务限流",
                "unavailable": "服务不可用",
            }.get(status, "服务错误")
            warnings.append(f"{request_id}：{label}，已降级为离线规则分析。")
            for candidate_id in candidate_ids:
                statuses[candidate_id] = f"{label}，已降级"
            continue
        try:
            parsed = _parse_response_text(raw_response.get("text"), request)
        except AIServiceResponseError as exc:
            warnings.append(f"{request_id}：结构化响应无效（{exc}），已降级。")
            for candidate_id in candidate_ids:
                statuses[candidate_id] = "响应无效，已降级"
            continue
        for candidate_id, analysis in parsed.items():
            if candidate_id in analyses:
                warnings.append(f"{request_id}：候选编号重复，已拒绝重复结果。")
                analyses.pop(candidate_id, None)
                statuses[candidate_id] = "响应重复，已降级"
                continue
            analyses[candidate_id] = analysis
            statuses[candidate_id] = "AI辅助分析完成"

    for request_id in sorted(set(expected) - seen_requests):
        warnings.append(f"{request_id}：响应缺失，已降级为离线规则分析。")
    return AIServiceOutcome(analyses, tuple(warnings), statuses)


def apply_ai_service_outcome(records: list[dict[str, Any]], outcome: AIServiceOutcome) -> None:
    """Apply only low-risk suggestions; never change fees, responsibility or closure."""

    for record in records:
        candidate_id = str(record.get("ai_candidate_id") or "")
        if not candidate_id:
            if record.get("included_in_summary"):
                record["analysis_status"] = "离线规则分析完成（无需AI辅助）"
                record["analysis_note"] = "规则证据充分，本案未发送到AI服务"
            continue
        status = outcome.candidate_status.get(candidate_id, "未返回，已降级")
        record["ai_service_status"] = status
        analysis = outcome.analyses.get(candidate_id)
        if analysis is None:
            record["issue_analysis_source"] = "rules"
            record["analysis_status"] = "AI不可用，已降级为离线规则"
            record["analysis_note"] = f"{status}；保留规则结果和三项人工复核"
            record["needs_review"] = True
            continue

        record["api_analysis"] = analysis
        record["issue_types"] = list(analysis["issue_types"])
        record["primary_issue_type"] = analysis["primary_issue_type"]
        record["issue_reason_summary"] = analysis["reason_summary"]
        record["issue_confidence"] = analysis["confidence"]
        record["issue_evidence"] = {"ai_evidence_refs": list(analysis["evidence_refs"])}
        record["issue_analysis_source"] = "api"
        record["ai_review_suggestion"] = analysis["review_suggestion"]
        record["analysis_status"] = "AI辅助分析完成（待人工复核）"
        record["analysis_note"] = "AI仅辅助问题类型与原因，费用、责任工厂和结案状态未由AI修改"
        record["needs_review"] = True


def _candidate_payload(record: dict[str, Any]) -> dict[str, Any]:
    candidate_id = _candidate_id(record)
    evidence_items: list[dict[str, str]] = []
    sections = (
        ("feedback", "客户反馈摘要"),
        ("investigation", "售后调查摘要"),
        ("application", "方案申请摘要"),
        ("solution", "解决方案摘要"),
    )
    for key, label in sections:
        text = _clean_text(record.get(key), 350)
        if not text:
            continue
        evidence_items.append(
            {
                "evidence_id": f"{candidate_id}-E{len(evidence_items) + 1}",
                "label": label,
                "text": text,
            }
        )
    combined = "；".join(item["text"] for item in evidence_items)
    if len(combined) > MAX_SUMMARY_CHARS:
        combined = combined[:MAX_SUMMARY_CHARS]
    return {
        "candidate_id": candidate_id,
        "complaint_summary": combined,
        "candidate_issue_types": _normalized_issue_types(record.get("issue_types")) or ["其他"],
        "primary_issue_type": (
            str(record.get("primary_issue_type"))
            if str(record.get("primary_issue_type")) in ISSUE_CATEGORIES
            else "其他"
        ),
        "rule_evidence": evidence_items,
        "fee_candidate": {
            "amount": _safe_amount(record.get("enterprise_cost_amount")),
            "status": _clean_text(record.get("enterprise_cost_status"), 40),
        },
        "necessary_context": {
            "product": _clean_text(record.get("product"), 160),
            "rule_reason": _clean_text(record.get("issue_reason_summary"), 500),
        },
    }


def _request_payload(batch_id: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": AI_RESPONSE_SCHEMA_VERSION,
        "batch_id": batch_id,
        "instruction": (
            "你只负责辅助判断投诉类型、概括产生售后的具体原因、引用给定证据编号并给出"
            "人工复核建议。不得判断或修改品牌、售后费用、责任工厂、赔偿审批、责任认定、"
            "解决状态或结案状态。不得补充输入中不存在的事实。只返回符合response_schema"
            "的JSON对象，不要Markdown或额外说明；analyses须逐一覆盖全部candidate_id。"
        ),
        "response_schema": {
            "schema_version": "1.0",
            "batch_id": batch_id,
            "analyses": [
                {
                    "candidate_id": "原样返回",
                    "issue_types": ["性能|外观|加工|其他"],
                    "primary_issue_type": "性能|外观|加工|其他",
                    "reason_summary": "基于给定证据的具体原因或故障现象",
                    "evidence_refs": ["只能引用该候选rule_evidence中的evidence_id"],
                    "review_suggestion": "给人工复核人员的简短建议",
                    "confidence": "0到1数字",
                }
            ],
        },
        "candidates": candidates,
    }


def _parse_response_text(text: Any, request: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        raise AIServiceResponseError("响应文本为空")
    cleaned = _CODE_FENCE_RE.sub("", text.strip()).strip()
    try:
        payload = json.loads(cleaned, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, AIServiceResponseError) as exc:
        raise AIServiceResponseError("不是有效JSON对象") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "batch_id",
        "analyses",
    }:
        raise AIServiceResponseError("顶层字段不符合严格合同")
    if payload["schema_version"] != AI_RESPONSE_SCHEMA_VERSION:
        raise AIServiceResponseError("schema_version不匹配")
    if payload["batch_id"] != request["payload"]["batch_id"]:
        raise AIServiceResponseError("batch_id不匹配")
    if not isinstance(payload["analyses"], list):
        raise AIServiceResponseError("analyses不是数组")

    candidates = {
        str(item["candidate_id"]): item for item in request["payload"]["candidates"]
    }
    parsed: dict[str, dict[str, Any]] = {}
    for raw in payload["analyses"]:
        analysis = _validate_analysis(raw, candidates)
        candidate_id = str(analysis.pop("candidate_id"))
        if candidate_id in parsed:
            raise AIServiceResponseError("candidate_id重复")
        parsed[candidate_id] = analysis
    if set(parsed) != set(candidates):
        raise AIServiceResponseError("没有逐一覆盖全部候选")
    return parsed


def _validate_analysis(
    raw: Any, candidates: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != _ALLOWED_ANALYSIS_FIELDS:
        raise AIServiceResponseError("案件字段不符合严格合同")
    candidate_id = str(raw.get("candidate_id") or "").strip()
    candidate = candidates.get(candidate_id)
    if candidate is None:
        raise AIServiceResponseError("candidate_id未知")
    raw_issue_types = raw.get("issue_types")
    if (
        not isinstance(raw_issue_types, list)
        or not raw_issue_types
        or len(raw_issue_types) != len(set(map(str, raw_issue_types)))
        or any(str(item).strip() not in ISSUE_CATEGORIES for item in raw_issue_types)
    ):
        raise AIServiceResponseError("issue_types含未知、重复或空类型")
    issue_types = _normalized_issue_types(raw.get("issue_types"))
    primary = str(raw.get("primary_issue_type") or "").strip()
    if primary not in issue_types:
        raise AIServiceResponseError("primary_issue_type不在issue_types中")
    reason_summary = _required_short(raw.get("reason_summary"), "reason_summary", 1_000)
    review_suggestion = _required_short(
        raw.get("review_suggestion"), "review_suggestion", 500
    )
    evidence_refs = raw.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs or len(evidence_refs) > 20:
        raise AIServiceResponseError("evidence_refs无效")
    allowed_refs = {
        str(item["evidence_id"]) for item in candidate.get("rule_evidence", [])
    }
    normalized_refs = [str(item) for item in evidence_refs]
    if (
        len(normalized_refs) != len(set(normalized_refs))
        or not set(normalized_refs) <= allowed_refs
    ):
        raise AIServiceResponseError("evidence_refs含未知或重复证据编号")
    confidence = _number(raw.get("confidence"), "confidence")
    if not 0 <= confidence <= 1:
        raise AIServiceResponseError("confidence必须在0到1之间")
    return {
        "candidate_id": candidate_id,
        "issue_types": issue_types,
        "primary_issue_type": primary,
        "reason_summary": reason_summary,
        "evidence_refs": normalized_refs,
        "review_suggestion": review_suggestion,
        "confidence": confidence,
    }


def _candidate_id(record: dict[str, Any]) -> str:
    digest = str(record.get("file_sha256") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        digest = hashlib.sha256(
            str(record.get("source_file") or "").encode("utf-8")
        ).hexdigest()
    try:
        input_index = max(0, int(record.get("input_index") or 0))
    except (TypeError, ValueError):
        input_index = 0
    return f"after-sales-{digest[:16].lower()}-{input_index:04d}"


def _batch_id(root_job_id: str, index: int, candidates: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        {"root_job_id": root_job_id, "index": index, "candidates": candidates},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _payload_size(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _normalized_issue_types(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        label = str(item).strip()
        if label not in ISSUE_CATEGORIES or label in result:
            continue
        result.append(label)
    return result


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    text = _EMAIL_RE.sub("[邮箱已脱敏]", text)
    text = _PHONE_RE.sub("[手机号已脱敏]", text)
    text = _LOCAL_PATH_RE.sub("[本地路径已脱敏]", text)
    text = _COMPANY_RE.sub("[企业名称已脱敏]", text)
    text = _IDENTITY_LABEL_RE.sub("[身份信息已脱敏]", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _required_short(value: Any, field: str, limit: int) -> str:
    text = _clean_text(value, limit)
    if not text:
        raise AIServiceResponseError(f"{field}为空")
    return text


def _safe_amount(value: Any) -> float | None:
    if value in {None, ""} or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, 2)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise AIServiceResponseError(f"{field}不是数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AIServiceResponseError(f"{field}不是数字") from exc
    if not math.isfinite(number):
        raise AIServiceResponseError(f"{field}不是有限数字")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AIServiceResponseError(f"JSON字段重复：{key}")
        result[key] = value
    return result

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
AUTO_MODEL = "auto"

MODEL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": AUTO_MODEL,
        "name": "自动选择",
        "description": "普通售后任务使用快速版，复杂或深度推理任务使用专业版",
        "recommended": False,
    },
    {
        "id": "deepseek-v4-flash",
        "name": "深度求索 V4 快速版",
        "description": "响应快、成本低，适合日常售后回复和工单整理",
        "recommended": True,
    },
    {
        "id": "deepseek-v4-pro",
        "name": "深度求索 V4 专业版",
        "description": "能力更强，适合复杂质量分析和多步骤处理方案",
        "recommended": False,
    },
)

ALLOWED_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


class DeepSeekGatewayError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GatewayConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    max_retries: int = 4
    retry_base_delay: float = 1.0

    @classmethod
    def from_mapping(cls, config: dict[str, Any] | None = None) -> GatewayConfig:
        values = config or {}
        api_key = str(
            values.get("api_key")
            or os.environ.get("AFTER_SALES_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or ""
        ).strip()
        if not api_key:
            raise DeepSeekGatewayError(
                "未配置 DeepSeek API Key；请设置 DEEPSEEK_API_KEY，"
                "或发送 X-DeepSeek-API-Key 请求头。",
                401,
            )
        base_url = str(
            values.get("base_url")
            or os.environ.get("AFTER_SALES_API_BASE_URL")
            or os.environ.get("DEEPSEEK_BASE_URL")
            or DEFAULT_BASE_URL
        ).strip()
        model = str(
            values.get("model")
            or os.environ.get("AFTER_SALES_API_MODEL")
            or os.environ.get("DEEPSEEK_MODEL")
            or DEFAULT_MODEL
        ).strip()
        try:
            timeout = float(values.get("timeout", os.environ.get("DEEPSEEK_TIMEOUT", 120)))
        except (TypeError, ValueError) as exc:
            raise DeepSeekGatewayError("timeout 必须是数字。", 400) from exc
        try:
            max_retries = int(values.get("max_retries", os.environ.get("DEEPSEEK_MAX_RETRIES", 4)))
            retry_base_delay = float(
                values.get("retry_base_delay", os.environ.get("DEEPSEEK_RETRY_BASE_DELAY", 1.0))
            )
        except (TypeError, ValueError) as exc:
            raise DeepSeekGatewayError("重试次数和重试间隔必须是数字。", 400) from exc
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model or DEFAULT_MODEL,
            timeout=max(1.0, min(timeout, 900.0)),
            max_retries=max(0, min(max_retries, 10)),
            retry_base_delay=max(0.0, min(retry_base_delay, 30.0)),
        )


def api_is_configured(config: dict[str, Any] | None = None) -> bool:
    values = config or {}
    return bool(
        values.get("api_key")
        or os.environ.get("AFTER_SALES_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )


def public_model_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in MODEL_CATALOG]


def chat_completions_url(base_url: str) -> str:
    value = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/chat/completions"


def resolve_model(
    requested_model: str | None, input_value: Any, reasoning_effort: str = "medium"
) -> str:
    requested = (requested_model or DEFAULT_MODEL).strip()
    if requested != AUTO_MODEL:
        return requested
    input_size = len(_input_as_text(input_value))
    if reasoning_effort in {"high", "xhigh", "max"} or input_size >= 6000:
        return "deepseek-v4-pro"
    return "deepseek-v4-flash"


def create_model_response(
    request_payload: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise DeepSeekGatewayError("请求体必须是 JSON 对象。", 400)

    input_value = request_payload.get("input")
    if input_value is None:
        input_value = request_payload.get("messages")
    if input_value is None or input_value == "" or input_value == []:
        raise DeepSeekGatewayError("input 或 messages 不能为空。", 400)

    effort = str(request_payload.get("reasoning_effort") or "medium").strip().lower()
    if effort not in ALLOWED_REASONING_EFFORTS:
        allowed = ", ".join(sorted(ALLOWED_REASONING_EFFORTS))
        raise DeepSeekGatewayError(f"reasoning_effort 不支持，可选值：{allowed}", 400)

    gateway_config = GatewayConfig.from_mapping(config)
    requested_model = str(
        request_payload.get("model") or gateway_config.model or DEFAULT_MODEL
    ).strip()
    resolved_model = resolve_model(requested_model, input_value, effort)
    messages = _normalize_messages(input_value)
    instructions = str(request_payload.get("instructions") or "").strip()
    if instructions:
        messages.insert(0, {"role": "system", "content": instructions})

    upstream_payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
    }
    if effort in {"none", "minimal", "low"}:
        upstream_payload["thinking"] = {"type": "disabled"}
    else:
        upstream_payload["thinking"] = {"type": "enabled"}
        upstream_payload["reasoning_effort"] = "max" if effort in {"xhigh", "max"} else "high"

    max_tokens = request_payload.get("max_tokens", request_payload.get("max_output_tokens", 4096))
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError) as exc:
        raise DeepSeekGatewayError("max_tokens/max_output_tokens 必须是整数。", 400) from exc
    if not 1 <= max_tokens <= 384_000:
        raise DeepSeekGatewayError("max_tokens 必须在 1 到 384000 之间。", 400)
    upstream_payload["max_tokens"] = max_tokens

    for key in ("temperature", "top_p", "stop", "response_format", "tools", "tool_choice"):
        value = request_payload.get(key)
        if value is not None and value != "":
            upstream_payload[key] = value

    response_json = _post_json(
        chat_completions_url(gateway_config.base_url), upstream_payload, gateway_config
    )
    output_text, reasoning_content, finish_reason = extract_output_text(response_json)
    return {
        "id": response_json.get("id"),
        "object": "ai.gateway.response",
        "status": "completed"
        if finish_reason not in {"length", "content_filter", "insufficient_system_resource"}
        else finish_reason,
        "requested_model": requested_model,
        "model": response_json.get("model") or resolved_model,
        "output_text": output_text,
        "reasoning_content": reasoning_content,
        "usage": response_json.get("usage") or {},
        "created_at": response_json.get("created"),
    }


def extract_output_text(response_json: dict[str, Any]) -> tuple[str, str, str]:
    choices = response_json.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise DeepSeekGatewayError("DeepSeek API 响应中没有 choices。", 502)
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise DeepSeekGatewayError("DeepSeek API 响应中没有可用文本。", 502)
    reasoning = message.get("reasoning_content")
    return (
        content,
        reasoning if isinstance(reasoning, str) else "",
        str(choice.get("finish_reason") or "stop"),
    )


def _normalize_messages(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return [{"role": "user", "content": value}]
    if not isinstance(value, list):
        raise DeepSeekGatewayError("input/messages 必须是字符串或消息数组。", 400)
    messages: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise DeepSeekGatewayError("消息数组中的每一项都必须是 JSON 对象。", 400)
        role = str(item.get("role") or "")
        if role == "developer":
            role = "system"
        if role not in {"system", "user", "assistant", "tool"}:
            raise DeepSeekGatewayError("消息 role 只支持 system、user、assistant、tool。", 400)
        content = item.get("content")
        if not isinstance(content, str):
            raise DeepSeekGatewayError("DeepSeek 消息 content 必须是字符串。", 400)
        normalized = {"role": role, "content": content}
        for key in ("name", "tool_call_id", "tool_calls"):
            if item.get(key) is not None:
                normalized[key] = item[key]
        messages.append(normalized)
    return messages


def _post_json(url: str, payload: dict[str, Any], config: GatewayConfig) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    raw = ""
    for attempt in range(config.max_retries + 1):
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {config.api_key}")
        request.add_header("User-Agent", "after-sales-deepseek-gateway/1.1")
        try:
            with urllib.request.urlopen(request, timeout=config.timeout) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            transient = exc.code == 429 or 500 <= exc.code <= 599
            if transient and attempt < config.max_retries:
                _sleep_before_retry(
                    attempt, config, exc.headers.get("Retry-After") if exc.headers else None
                )
                continue
            message = _upstream_error_message(detail) or f"DeepSeek API HTTP {exc.code}"
            status = exc.code if 400 <= exc.code < 500 else 502
            raise DeepSeekGatewayError(message, status) from exc
        except urllib.error.URLError as exc:
            if attempt < config.max_retries:
                _sleep_before_retry(attempt, config)
                continue
            raise DeepSeekGatewayError(f"无法连接 DeepSeek API：{exc.reason}", 502) from exc
        except TimeoutError as exc:
            if attempt < config.max_retries:
                _sleep_before_retry(attempt, config)
                continue
            raise DeepSeekGatewayError("DeepSeek API 请求超时。", 504) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeepSeekGatewayError("DeepSeek API 返回了无效 JSON。", 502) from exc
    if not isinstance(parsed, dict):
        raise DeepSeekGatewayError("DeepSeek API 返回格式无效。", 502)
    return parsed


def _sleep_before_retry(
    attempt: int, config: GatewayConfig, retry_after: str | None = None
) -> None:
    delay: float | None = None
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = None
    if delay is None:
        delay = config.retry_base_delay * (2**attempt)
    time.sleep(max(0.0, min(delay, 30.0)))


def _upstream_error_message(raw: str) -> str:
    try:
        parsed = json.loads(raw)
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:1000]
    except json.JSONDecodeError:
        pass
    return raw.strip()[:1000]


def _input_as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)

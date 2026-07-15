from __future__ import annotations

import json
import re
import time
from typing import Any

from after_sales_agent.deepseek_gateway import (
    api_is_configured,
    create_model_response,
)

ISSUE_CATEGORIES = ["性能", "外观", "加工", "其他"]


def analyze_issue_with_api(
    fields: dict[str, str],
    rules: dict[str, Any],
    api_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return analyze_after_sales_with_api(fields, rules, api_config)


def analyze_after_sales_with_api(
    fields: dict[str, str],
    rules: dict[str, Any],
    api_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = api_config or {}
    categories = list(rules.get("issue_order", ISSUE_CATEGORIES))
    request = {
        "model": config.get("model"),
        "reasoning_effort": config.get("reasoning_effort") or "medium",
        "instructions": (
            "你是竹材料公司品质售后数据分析助手。"
            "必须只依据用户提供的 Excel 抽取原文进行结构化分析，不能编造事实。"
            "返回严格 JSON，不要 Markdown。"
        ),
        "input": build_prompt(fields, categories),
        "max_output_tokens": 3000,
        "store": False,
    }
    attempts = max(1, min(int(config.get("max_attempts") or 3), 5))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = create_model_response(request, config)
            parsed = parse_json_content(response["output_text"])
            break
        except Exception as exc:
            last_error = exc
            status_code = int(getattr(exc, "status_code", 0) or 0)
            if 400 <= status_code < 500 or attempt + 1 >= attempts:
                raise
            time.sleep(min(2**attempt, 4))
    else:
        raise RuntimeError(f"API分析失败：{last_error}")
    normalized = normalize_analysis(parsed, categories)
    normalized["model"] = response["model"]
    normalized["response_id"] = response["id"]
    return normalized


def build_prompt(fields: dict[str, str], categories: list[str]) -> str:
    text_parts = [
        f"来源文件名：{fields.get('source_file', '')}",
        f"客户/项目：{fields.get('customer', '')}",
        f"地点：{fields.get('location', '')}",
        f"销售/代表：{fields.get('salesperson', '')}",
        f"售后日期字段：{fields.get('complaint_date', '')}",
        f"产品名称：{fields.get('product', '')}",
        f"规格：{fields.get('spec', '')}",
        f"订单：{fields.get('order_no', '')}",
        f"交货日期：{fields.get('delivery_date', '')}",
        f"反馈内容：{fields.get('feedback', '')}",
        f"方案申请明细：{fields.get('application', '')}",
        f"售后负责人调查情况：{fields.get('investigation', '')}",
        f"售后解决方案：{fields.get('solution', '')}",
        f"责任落实：{fields.get('responsibility', '')}",
        f"工作簿完整原文（用于兼容不同模板和表格布局）：\n{fields.get('raw_text', '')}",
    ]
    return f"""
请把下面售后Excel原文分析成一条结构化售后记录。所有业务判断都必须由你根据原文完成。

你需要判断：
1. brand_name：只填写产品品牌或品牌方名称。品牌和客户/项目是两个不同字段，严禁把客户名称、项目名称、公司名称或地点当作品牌。来源文件名、产品名称、方案申请明细或其他原文中明确出现的品牌可以作为证据；否则一律填“未知”。品牌不是固定列表，可以返回任何有原文证据的新品牌，不得为了凑已有品牌而强行归类。
2. after_sales_year / after_sales_month：只能从“售后日期字段”（即提出质量问题日期、报修日期或投诉日期）读取。严禁用订单日期、交货日期、来源文件名中的日期或文件时间代替。日期只写了月日而没有年份时，after_sales_year 必须填 null，after_sales_month 按原字段填写；字段为空或无法判断时均填 null。
3. issue_types：问题原因类型，只能从 {", ".join(categories)} 中选择，可以多选。
4. primary_issue_type：最主要的问题原因类型，只能选一个。
5. selected_solution：提取最终采用的售后解决方案。若调查中列出多个备选方案，必须以“售后解决方案”栏最终明确采用的方案为准，不得把未采用方案混入。
6. cost_items：只提取最终采用方案所需的售后费用，包括材料费、人工费、差旅费、运费、返工费、补发成本和赔偿等。每项必须包含名称、金额、是否纳入本公司统计、原文证据。
7. cost_amount：只作为模型候选金额，最终金额由后端确定性复核。费用取值优先级为“售后解决方案”明确金额 > “方案申请明细”明确金额 > “售后负责人调查情况”中与最终方案对应的金额 > “反馈内容”。若原文已有总计/合计/小计，优先采用明确总额；不要把未采用备选方案、单价、数量、中间数和公式结果重复相加。没有明确金额必须填 null，绝不能填 0；只有原文明确定义费用为0元时才填0。
8. cost_included：如果全部费用均转嫁给供应商/合作方或原文明确不纳入统计，填 false；否则填 true。费用由本公司多个部门承担仍应纳入。转嫁但金额未知时 cost_amount 仍为 null。
9. resolution_status：只能填写“已解决”“处理中”“未解决”。只有原文明确表示已经完成更换、返工、处理、客户自行解决或已经结案，才能填“已解决”；只是“建议执行、下售后单、重新生产、补数生产、安排人员、待更换/返修”时填“处理中”；没有解决方案或仍要求出方案时填“未解决”。不得把“已经确定方案”等同于“已经实际解决”。

分类口径：
- 性能：开裂、分层、发霉、腐烂、变形、强度、耐候、稳定性等材料或产品性能问题。
- 外观：颜色、色差、漆面、表面、划伤、崩边、脏污、观感等问题。
- 加工：尺寸、规格、开片、加工、图纸拆解、生产指令、补数、安装适配等制造或设计执行问题。
- 其他：无法归入以上三类，或证据不足。

要求：
- evidence 必须引用原文中的短句或关键词。
- reason_summary 必须综合且仅依据“反馈内容、方案申请明细、售后负责人调查情况、售后解决方案”提取“产生售后的具体原因”，其中根因优先采用售后负责人调查情况；要区分客户看到的现象与根本原因。例如原文有“开片指令错误”“设计遗漏”“低温收缩与金属柱不一致导致胀裂”时，应直接写入原因，不能只重复“性能/外观/加工”分类。
- 原文只有现象而没有根因时，reason_summary 应如实写具体故障现象，并注明“原表未写明根因”，不能编造。
- confidence 是 0 到 1 的数字，表示整条结构化判断的置信度。
- 不要输出解释文字，只输出严格JSON。

JSON格式：
{{
  "brand_name": "桃花江",
  "brand_reason": "从产品名称或原文识别出的依据",
  "after_sales_year": 2026,
  "after_sales_month": 5,
  "issue_types": ["性能"],
  "primary_issue_type": "性能",
  "reason_summary": "从原表提取的具体售后原因或故障现象",
  "evidence": ["原文证据1", "原文证据2"],
  "selected_solution": "最终采用的解决方案",
  "cost_items": [
    {{"name": "材料费", "amount": 2500, "included": true, "evidence": "材料费用2500元"}},
    {{"name": "运费", "amount": 430, "included": true, "evidence": "运费430元"}}
  ],
  "cost_amount": 2930,
  "cost_included": true,
  "cost_reason": "费用判断依据",
  "resolution_status": "处理中",
  "resolution_reason": "解决状态判断依据",
  "confidence": 0.9,
  "needs_manual_review": false
}}

售后Excel原文：
{chr(10).join(text_parts)}
""".strip()


def parse_json_content(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    match = re.search(r"\{.*\}", content, re.S)
    if match:
        content = match.group(0)
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("API returned non-object JSON")
    return parsed


def normalize_analysis(parsed: dict[str, Any], categories: list[str]) -> dict[str, Any]:
    raw_types = parsed.get("issue_types") or []
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    issue_types: list[str] = []
    for item in raw_types:
        normalized = normalize_category(str(item), categories)
        if normalized and normalized not in issue_types:
            issue_types.append(normalized)
    if not issue_types:
        issue_types = ["其他"]

    primary = normalize_category(str(parsed.get("primary_issue_type") or issue_types[0]), categories) or issue_types[0]
    evidence = parsed.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]

    cost_items = normalize_cost_items(parsed.get("cost_items"))
    resolution_status = normalize_resolution_status(
        parsed.get("resolution_status"), parsed.get("closed")
    )

    return {
        "brand_name": normalize_brand_name(parsed.get("brand_name")),
        "brand_reason": clean_text(parsed.get("brand_reason")),
        "after_sales_year": parse_optional_int(parsed.get("after_sales_year")),
        "after_sales_month": parse_month(parsed.get("after_sales_month")),
        "issue_types": issue_types,
        "primary_issue_type": primary,
        "reason_summary": clean_text(parsed.get("reason_summary")),
        "evidence": [clean_text(item) for item in evidence if clean_text(item)][:8],
        "selected_solution": clean_text(parsed.get("selected_solution")),
        "cost_items": cost_items,
        "cost_amount": parse_optional_float(parsed.get("cost_amount"), default=None),
        "cost_included": parse_bool(parsed.get("cost_included"), True),
        "cost_reason": clean_text(parsed.get("cost_reason")),
        "resolution_status": resolution_status,
        "resolution_reason": clean_text(
            parsed.get("resolution_reason") or parsed.get("closed_reason")
        ),
        "closed": resolution_status == "已解决",
        "closed_reason": clean_text(
            parsed.get("resolution_reason") or parsed.get("closed_reason")
        ),
        "confidence": clamp_float(parsed.get("confidence"), 0.0, 1.0),
        "needs_manual_review": parse_bool(parsed.get("needs_manual_review"), clamp_float(parsed.get("confidence"), 0.0, 1.0) < 0.7),
}


def normalize_brand_name(value: Any) -> str:
    text = clean_text(value)
    if not text or text in {"未识别", "无法识别", "无法判断", "不明确", "无", "null", "None"}:
        return "未知"
    return text


def normalize_resolution_status(value: Any, legacy_closed: Any = None) -> str:
    text = clean_text(value)
    if text in {"已解决", "处理中", "未解决"}:
        return text
    if text in {"完成", "已完成", "已处理", "已关闭", "结案"}:
        return "已解决"
    if text in {"待处理", "进行中", "执行中", "待执行"}:
        return "处理中"
    if text in {"未处理", "无方案"}:
        return "未解决"
    return "已解决" if parse_bool(legacy_closed, False) else "未解决"


def normalize_category(value: str, categories: list[str]) -> str | None:
    value = value.strip()
    if value in categories:
        return value
    mapping = {
        "加工": "加工",
        "尺寸": "加工",
        "安装": "加工",
        "功能": "加工",
        "功能性": "加工",
        "质量": "性能",
        "材料": "性能",
        "观感": "外观",
    }
    if value in mapping and mapping[value] in categories:
        return mapping[value]
    for category in categories:
        if category in value:
            return category
    return None


def normalize_cost_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "name": clean_text(item.get("name")) or "售后费用",
                "amount": parse_optional_float(item.get("amount"), default=0.0),
                "included": parse_bool(item.get("included"), True),
                "evidence": clean_text(item.get("evidence")),
            }
        )
    return items


def parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_month(value: Any) -> int | None:
    month = parse_optional_int(value)
    if month and 1 <= month <= 12:
        return month
    return None


def parse_optional_float(value: Any, default: float | None = 0.0) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "是", "已", "已完成"}:
        return True
    if text in {"false", "0", "no", "n", "否", "未", "未完成"}:
        return False
    return default


def clean_text(value: Any) -> str:
    return str(value or "").strip()

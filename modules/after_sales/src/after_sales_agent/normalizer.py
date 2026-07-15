from __future__ import annotations

import ast
import operator
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


AMOUNT_RE = re.compile(r"(?<!\d)(-?\d+(?:\.\d+)?)\s*元")
RESULT_RE = re.compile(r"=\s*(-?\d+(?:\.\d+)?)\s*元")
TOTAL_ANCHORS = (
    "合计总费用", "本次售后费用", "材料合计费用", "损失合计", "费用合计",
    "合计费用", "总计", "共计", "总费用", "小计费用",
)
TRANSFER_MARKERS = ("转嫁", "并在", "并入其他订单", "供应商承担", "合作方承担")
ESTIMATE_MARKERS = ("预计", "预估", "约", "暂估")


@dataclass
class FeeResult:
    amount: float | None
    status: str
    evidence: str
    items: list[dict[str, Any]]
    included: bool
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def determine_fee(fields: dict[str, Any], rules: dict[str, Any]) -> FeeResult:
    """Deterministically verify the final fee; model output is never trusted as the total."""
    final_solution = clean_text(fields.get("solution"))
    feedback = clean_text(fields.get("feedback"))
    application = clean_text(fields.get("application"))

    # A proposed repair cost is not a final incurred cost when the source explicitly
    # says the customer handled the issue themselves. Keep it unknown for review.
    if (
        application
        and extract_amounts(application)
        and (
            "未采用" in final_solution
            or re.search(r"客户自己.{0,20}(解决|处理)|自行.{0,20}(解决|处理)", f"{feedback} {final_solution}")
        )
        and not extract_amounts(final_solution)
    ):
        return FeeResult(
            None,
            "needs_review",
            "方案申请中存在候选金额，但反馈显示客户自行处理，最终实际费用无法确认",
            [],
            False,
            ["候选费用可能未实际发生，请人工确认"],
        )

    sources = [
        ("售后解决方案", final_solution),
        ("方案申请明细", application),
        ("售后负责人调查情况", clean_text(fields.get("investigation"))),
        ("反馈内容", feedback),
        ("工作簿原文", clean_text(fields.get("raw_text"))),
    ]
    for label, text in sources:
        if not text:
            continue
        result = analyze_fee_text(text, label, rules)
        if result.status != "not_found":
            return result
    return FeeResult(None, "not_found", "原文未找到可确认的售后费用", [], False, ["费用待确认"])


def analyze_fee_text(text: str, label: str, rules: dict[str, Any]) -> FeeResult:
    normalized = normalize_formula_text(text)
    has_transfer = any(marker in normalized for marker in TRANSFER_MARKERS)
    amounts = extract_amounts(normalized)
    if has_transfer and not amounts:
        return FeeResult(
            None,
            "transferred",
            f"{label}：写明费用转嫁/并入其他订单，但没有可确认金额",
            [],
            False,
            ["费用承担方式已说明，但金额未知"],
        )
    if not amounts:
        if re.search(r"(无|没有|未产生).{0,5}(售后)?费用|费用.{0,5}(为|是)?\s*0\s*元", normalized):
            return FeeResult(0.0, "exact", f"{label}：原文明确定义费用为0元", [], True, [])
        return FeeResult(None, "not_found", "", [], False, [])

    # Prefer an explicit final total anchor. The last amount in the same sentence
    # is normally the declared total and prevents subtotal + total double counting.
    total_candidates: list[tuple[float, str]] = []
    for sentence in split_sentences(normalized):
        sentence_amounts = extract_amounts(sentence)
        if sentence_amounts and any(anchor in sentence for anchor in TOTAL_ANCHORS):
            total_candidates.append((sentence_amounts[-1], sentence.strip()))
    if total_candidates:
        unique = unique_amounts([item[0] for item in total_candidates])
        if len(unique) > 1:
            # A later grand-total anchor wins over earlier subtotals; otherwise flag conflict.
            grand = [item for item in total_candidates if "合计总费用" in item[1] or "总费用" in item[1]]
            if grand:
                value, evidence = grand[-1]
            else:
                return FeeResult(
                    None,
                    "needs_review",
                    f"{label}：发现多个冲突总计：{', '.join(format_number(v) for v in unique)}元",
                    [],
                    not has_transfer,
                    ["多个费用总计冲突"],
                )
        else:
            value, evidence = total_candidates[-1]
        status = "estimated" if any(marker in evidence for marker in ESTIMATE_MARKERS) else "exact"
        verified = verify_formula_in_text(evidence)
        tolerance = max(0.15, abs(value) * 0.0002)
        if verified is not None and abs(verified - value) > tolerance:
            return FeeResult(None, "needs_review", f"{label}：算式与等号后金额不一致：{evidence}", [], False, ["费用算式不一致"])
        return FeeResult(
            round(value, 2),
            status,
            f"{label}：{evidence[:260]}",
            [{"name": "最终总费用", "amount": round(value, 2), "evidence": evidence[:260]}],
            not has_transfer,
            [],
        )

    formula_results: list[tuple[float, str]] = []
    for sentence in split_sentences(normalized):
        for match in RESULT_RE.finditer(sentence):
            formula_results.append((float(match.group(1)), sentence.strip()))
    if formula_results:
        values = unique_amounts([item[0] for item in formula_results])
        value = round(sum(values), 2)
        warnings: list[str] = []
        for _, evidence in formula_results:
            verified = verify_formula_in_text(evidence)
            if verified is not None:
                declared = float(RESULT_RE.search(evidence).group(1))  # type: ignore[union-attr]
                tolerance = max(0.15, abs(declared) * 0.0002)
                if abs(verified - declared) > tolerance:
                    warnings.append(f"算式不一致：{evidence[:120]}")
        if warnings:
            return FeeResult(None, "needs_review", f"{label}：发现费用算式冲突", [], False, warnings)
        items = [
            {"name": f"费用分项{index}", "amount": round(amount, 2), "evidence": evidence[:220]}
            for index, (amount, evidence) in enumerate(formula_results, start=1)
            if amount in values
        ]
        return FeeResult(value, "calculated", f"{label}：按明确算式合计 {format_number(value)} 元", items, not has_transfer, [])

    # A single amount with fee/loss context is usable. Multiple unanchored amounts are unsafe.
    fee_context = any(keyword in normalized for keyword in rules.get("cost_keywords", []))
    unique = unique_amounts(amounts)
    if fee_context and len(unique) == 1:
        value = unique[0]
        status = "estimated" if any(marker in normalized for marker in ESTIMATE_MARKERS) else "exact"
        return FeeResult(
            round(value, 2),
            status,
            f"{label}：识别到明确费用 {format_number(value)} 元",
            [{"name": "售后费用", "amount": round(value, 2), "evidence": normalized[:240]}],
            not has_transfer,
            [],
        )
    return FeeResult(
        None,
        "needs_review",
        f"{label}：存在多个候选金额，无法确定最终总费用",
        [],
        False,
        [f"候选金额：{', '.join(format_number(value) for value in unique)}元"],
    )


def build_date_warnings(
    after_sales_date: str | None,
    delivery_text: Any,
    order_text: Any,
) -> list[str]:
    if not after_sales_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", after_sales_date):
        return []
    try:
        reported = date.fromisoformat(after_sales_date)
    except ValueError:
        return ["售后日期格式无效"]
    warnings: list[str] = []
    delivery = parse_first_full_date(delivery_text)
    if delivery and reported < delivery:
        warnings.append(f"售后日期 {reported.isoformat()} 早于交货日期 {delivery.isoformat()}")
    order = parse_order_date(order_text)
    if order and reported < order:
        warnings.append(f"售后日期 {reported.isoformat()} 早于订单日期 {order.isoformat()}")
    return warnings


def parse_first_full_date(value: Any) -> date | None:
    text = clean_text(value)
    match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def parse_order_date(value: Any) -> date | None:
    text = clean_text(value)
    for match in re.finditer(r"(20\d{2})(\d{2})(\d{2})", text):
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            continue
    return None


def safe_calculate(expression: str) -> float:
    expression = normalize_formula_text(expression)
    expression = re.sub(r"[^0-9+\-*/().]", "", expression)
    if not expression or len(expression) > 300:
        raise ValueError("unsupported arithmetic expression")
    node = ast.parse(expression, mode="eval")
    operations = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def evaluate(current: ast.AST) -> float:
        if isinstance(current, ast.Expression):
            return evaluate(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, (int, float)):
            return float(current.value)
        if isinstance(current, ast.BinOp) and type(current.op) in operations:
            return float(operations[type(current.op)](evaluate(current.left), evaluate(current.right)))
        if isinstance(current, ast.UnaryOp) and type(current.op) in operations:
            return float(operations[type(current.op)](evaluate(current.operand)))
        raise ValueError("unsupported arithmetic node")

    return evaluate(node)


def verify_formula_in_text(text: str) -> float | None:
    if "=" not in text:
        return None
    left = text.rsplit("=", 1)[0]
    # Fee formulas are normally introduced by a Chinese/ASCII colon. Removing
    # unit words from that final clause preserves expressions such as 468元+180元.
    expression = re.split(r"[:：]", left)[-1]
    if not re.search(r"[+\-*/×]", expression):
        return None
    try:
        return round(safe_calculate(expression), 2)
    except (ValueError, ZeroDivisionError, SyntaxError):
        return None


def normalize_formula_text(text: str) -> str:
    return (
        clean_text(text)
        .replace("×", "*")
        .replace("X", "*")
        .replace("x", "*")
        .replace("＊", "*")
        .replace("＝", "=")
        .replace("（", "(")
        .replace("）", ")")
        .replace("－", "-")
        .replace("—", "-")
    )


def extract_amounts(text: str) -> list[float]:
    return [float(match.group(1)) for match in AMOUNT_RE.finditer(text)]


def unique_amounts(values: list[float]) -> list[float]:
    unique: list[float] = []
    for value in values:
        rounded = round(float(value), 2)
        if rounded not in unique:
            unique.append(rounded)
    return unique


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。；;\n]", text) if part.strip()]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")

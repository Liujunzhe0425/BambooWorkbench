"""Build deterministic business confirmations without external services."""

from __future__ import annotations

import hashlib
import json

from moisture.domain.models import BusinessConfirmationIssue

_REASONS = {
    "sheet_ambiguity": "多个工作表同分，请确认用于水分分析的工作表",
    "supplier_mapping": "供应商映射存在多个候选，请确认业务名称",
    "department_mapping": "部门映射存在多个候选，请确认业务名称",
    "formula_conflict": "Excel 原始值与公式复核值不一致，请确认采用值",
    "rule_scope": "规则适用范围不确定，请确认是否适用于本批次",
}


def _normalized_candidates(issue: BusinessConfirmationIssue) -> tuple[str, ...]:
    return tuple(sorted({value.strip() for value in issue.candidates if value.strip()}))


def build_confirmations(
    root_job_id: str,
    issues: tuple[BusinessConfirmationIssue, ...],
) -> tuple[dict[str, object], ...]:
    """Map genuine module ambiguities to stable contract prompts."""

    prompts: list[dict[str, object]] = []
    for issue in issues:
        candidates = _normalized_candidates(issue)
        if not candidates:
            continue
        identity = json.dumps(
            {
                "root_job_id": root_job_id,
                "fingerprint": issue.fingerprint,
                "field": issue.field,
                "candidates": candidates,
                "rule_hash": issue.rule_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        confirmation_id = f"msr-confirm-{hashlib.sha256(identity).hexdigest()[:24]}"
        prompts.append(
            {
                "confirmation_id": confirmation_id,
                "field": issue.field,
                "reason": _REASONS[issue.kind],
                "suggested_value": issue.suggested_value,
                "options": list(candidates),
                "confidence": 0.5,
                "blocking": True,
                "batch_applicable": issue.kind in {"supplier_mapping", "department_mapping", "rule_scope"},
                "rememberable": issue.kind in {"supplier_mapping", "department_mapping"},
                "source": {
                    "source_file": str(issue.source_file),
                    "sheet": issue.sheet,
                    "cell_or_range": issue.cell_or_range,
                },
            }
        )
    return tuple(sorted(prompts, key=lambda item: str(item["confirmation_id"])))

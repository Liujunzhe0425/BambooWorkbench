from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.confirmation_builder import build_confirmations
from moisture.domain.models import BusinessConfirmationIssue


def issue(kind: str, candidates: tuple[str, ...], source: Path) -> BusinessConfirmationIssue:
    return BusinessConfirmationIssue(
        kind=kind,  # type: ignore[arg-type]
        fingerprint="a" * 64,
        field={
            "sheet_ambiguity": "source_sheet",
            "supplier_mapping": "supplier",
            "department_mapping": "department",
            "formula_conflict": "sample_1",
            "rule_scope": "rule_scope",
        }[kind],
        candidates=candidates,
        source_file=source,
        rule_hash="b" * 64,
    )


def test_representative_business_ambiguities_have_stable_path_independent_ids(tmp_path: Path) -> None:
    issues_a = tuple(
        issue(kind, values, tmp_path / "one" / "source.xlsx")
        for kind, values in (
            ("sheet_ambiguity", ("记录B", "记录A")),
            ("supplier_mapping", ("供应商乙", "供应商甲")),
            ("department_mapping", ("二厂", "品质部")),
            ("formula_conflict", ("0.5002", "0.5")),
            ("rule_scope", ("适用", "不适用")),
        )
    )
    issues_b = tuple(
        issue(item.kind, tuple(reversed(item.candidates)), tmp_path / "moved" / "source.xlsx")
        for item in issues_a
    )

    first = build_confirmations("draft-root", issues_a)
    second = build_confirmations("draft-root", issues_b)

    assert [item["confirmation_id"] for item in first] == [item["confirmation_id"] for item in second]
    assert len(first) == 5
    assert all("责任" not in str(item) and "不合格" not in str(item) for item in first)


def test_no_issue_means_no_confirmation() -> None:
    assert build_confirmations("draft-root", ()) == ()

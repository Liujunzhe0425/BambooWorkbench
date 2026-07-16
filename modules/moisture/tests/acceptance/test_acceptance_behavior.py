# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "acceptance"
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.excel.source_parser import ExcelSourceParser
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import run_draft
from moisture.application.service_response_validator import validate_ai_response_text
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode
from moisture.domain.statistics import compute_batch_statistics


def _expected() -> dict[str, object]:
    return json.loads((FIXTURES / "expected-behavior.json").read_text(encoding="utf-8"))


def test_synthetic_formula_statistics_and_rule_acceptance_cases() -> None:
    expected = _expected()
    parser = ExcelSourceParser()
    for name in ("normal", "high_suspect", "low_suspect"):
        path = FIXTURES / f"{name}.xlsx"
        before = path.read_bytes()
        record = parser.parse(path)
        statistics = compute_batch_statistics(record)
        case = expected[name]
        assert record.supplier == "脱敏供应方-A"
        assert record.material_type == "竹丝"
        assert len(record.samples) == case["sample_count"]
        assert statistics.mean == Decimal(case["mean"])
        if name == "normal":
            assert [item.value_used_for_statistics for item in record.samples] == [
                Decimal(value) for value in case["values"]
            ]
            assert statistics.minimum == Decimal(case["minimum"])
            assert statistics.maximum == Decimal(case["maximum"])
            assert statistics.range_value == Decimal(case["range_value"])
        outcome = DeterministicPipeline().run((path,))
        assert [item.direction for item in outcome.pending_rule_matches] == case[
            "pending_directions"
        ]
        assert path.read_bytes() == before


def test_corrupt_duplicate_and_eleven_sample_boundaries() -> None:
    expected = _expected()
    corrupt = DeterministicPipeline().run((FIXTURES / "corrupt.xlsx",))
    eleven = DeterministicPipeline().run((FIXTURES / "eleven_samples.xlsx",))
    duplicate = DeterministicPipeline().run(
        (FIXTURES / "normal.xlsx", FIXTURES / "duplicate_normal.xlsx")
    )

    assert corrupt.failed_count == expected["corrupt"]["failed_count"]
    assert eleven.failed_count == expected["eleven_samples"]["failed_count"]
    assert duplicate.processed_count == expected["duplicate_pair"]["processed_count"]
    assert duplicate.skipped_count == expected["duplicate_pair"]["skipped_count"]


def test_protocol_examples_cover_valid_ai_and_denied_degradation() -> None:
    protocol = MODULE_ROOT / "samples" / "protocol"
    request = json.loads((protocol / "ai-request.example.json").read_text(encoding="utf-8"))
    valid = json.loads((protocol / "ai-response-valid.example.json").read_text(encoding="utf-8"))
    denied = json.loads((protocol / "ai-response-denied.example.json").read_text(encoding="utf-8"))

    decisions = validate_ai_response_text(valid["responses"][0]["text"], request)
    assert decisions[0].confidence == Decimal("0.86")
    assert denied["responses"][0]["status"] == "denied"


def test_normal_draft_freezes_report_and_result_markers(tmp_path: Path) -> None:
    output = tmp_path / "output"
    job = JobRequest(
        "1.0",
        "acceptance-normal",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (FIXTURES / "normal.xlsx",),
        output,
    )

    assert run_draft(job) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    report = (output / "analysis_report.md").read_text(encoding="utf-8")
    markers = json.loads((FIXTURES / "expected-report-markers.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert all(marker in report for marker in markers["required"])
    assert all(marker not in report for marker in markers["forbidden"])


def test_acceptance_assets_are_synthetic_relative_and_secret_free() -> None:
    forbidden = ("D:\\", "C:\\Users\\", "api_key", "authorization: bearer")
    paths = list((MODULE_ROOT / "samples").rglob("*"))
    paths.extend(
        (MODULE_ROOT / "docs" / f"0{index}-{name}.md")
        for index, name in (
            (1, "业务说明"),
            (2, "输入字段与样本规则"),
            (3, "统计与公式口径"),
            (4, "规则与颜色判定"),
            (5, "AI与经验库说明"),
            (6, "验收与故障处理"),
        )
    )
    for path in paths:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore").casefold()
            assert all(item.casefold() not in text for item in forbidden), path
    for path in FIXTURES.glob("*.xlsx"):
        assert "2026年4月份" not in path.name

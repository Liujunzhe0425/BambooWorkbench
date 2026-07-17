# ruff: noqa: E402, I001

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "acceptance"
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.adapters.excel.source_parser import ExcelSourceParser
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import run_draft
from moisture.application.service_response_validator import validate_ai_response_text
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode
from moisture.domain.statistics import compute_batch_statistics

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _build_acceptance_workbooks(
    directory: Path,
    workbook_factory: Callable[..., Path],
) -> dict[str, Path]:
    common = {
        "supplier": "脱敏供应方-A",
        "material_type": "竹丝",
        "arrival_date": "2026-01-10",
        "test_date": "2026-01-11",
        "total_weight": "1000 kg",
    }
    paths = {
        "normal": workbook_factory(
            directory / "normal.xlsx",
            departments={"品质": 2},
            moisture_values=("0.5", "0.52"),
            mass_values=((100, 50, 0), (100, 48, 0)),
            **common,
        ),
        "high_suspect": workbook_factory(
            directory / "high_suspect.xlsx",
            moisture_values=("0.6",),
            mass_values=((100, 40, 0),),
            **common,
        ),
        "low_suspect": workbook_factory(
            directory / "low_suspect.xlsx",
            moisture_values=("0.4",),
            mass_values=((100, 60, 0),),
            **common,
        ),
        "eleven_samples": workbook_factory(
            directory / "eleven_samples.xlsx",
            departments={"品质": 11},
            moisture_values=tuple("0.5" for _ in range(11)),
            mass_values=tuple((100, 50, 0) for _ in range(11)),
            **common,
        ),
    }
    paths["duplicate_normal"] = directory / "duplicate_normal.xlsx"
    shutil.copyfile(paths["normal"], paths["duplicate_normal"])
    paths["corrupt"] = directory / "corrupt.xlsx"
    paths["corrupt"].write_bytes(b"not an Excel workbook")
    return paths


def _expected() -> dict[str, object]:
    return json.loads((FIXTURES / "expected-behavior.json").read_text(encoding="utf-8"))


def test_synthetic_formula_statistics_and_rule_acceptance_cases(
    tmp_path: Path,
    workbook_factory: Callable[..., Path],
) -> None:
    expected = _expected()
    workbooks = _build_acceptance_workbooks(tmp_path, workbook_factory)
    parser = ExcelSourceParser()
    for name in ("normal", "high_suspect", "low_suspect"):
        path = workbooks[name]
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
        assert outcome.pending_rule_matches == ()
        assert outcome.batches[0].final_display_color.value == case["display_color"]
        assert path.read_bytes() == before


def test_corrupt_duplicate_and_eleven_sample_boundaries(
    tmp_path: Path,
    workbook_factory: Callable[..., Path],
) -> None:
    expected = _expected()
    workbooks = _build_acceptance_workbooks(tmp_path, workbook_factory)
    corrupt = DeterministicPipeline().run((workbooks["corrupt"],))
    eleven = DeterministicPipeline().run((workbooks["eleven_samples"],))
    duplicate = DeterministicPipeline().run(
        (workbooks["normal"], workbooks["duplicate_normal"])
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


def test_normal_draft_freezes_report_and_result_markers(
    tmp_path: Path,
    workbook_factory: Callable[..., Path],
) -> None:
    workbooks = _build_acceptance_workbooks(tmp_path / "inputs", workbook_factory)
    output = tmp_path / "output"
    job = JobRequest(
        "1.0",
        "acceptance-normal",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (workbooks["normal"],),
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
    assert not list(FIXTURES.glob("*.xlsx"))

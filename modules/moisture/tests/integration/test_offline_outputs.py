from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.draft_orchestrator import run_draft  # noqa: E402
from moisture.contract.job_models import JobRequest  # noqa: E402

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _job(source: Path, output_dir: Path, *, ai_enabled: bool = False) -> JobRequest:
    return JobRequest.from_payload(
        {
            "schema_version": "1.0",
            "job_id": "job-t14-offline",
            "module_id": "moisture",
            "phase": "draft",
            "run_mode": "single",
            "input_files": [str(source.resolve())],
            "output_dir": str(output_dir.resolve()),
            "ai_enabled": ai_enabled,
        }
    )


def test_ai_disabled_still_produces_xlsx_markdown_and_result_last(
    tmp_path: Path, workbook_factory, monkeypatch
) -> None:
    source = workbook_factory(tmp_path / "source.xlsx", moisture_values=(0.50,))
    output_dir = tmp_path / "output"
    replacements: list[str] = []
    import os

    real_replace = os.replace

    def recording_replace(source_path, target_path):
        replacements.append(Path(target_path).name)
        return real_replace(source_path, target_path)

    monkeypatch.setattr(os, "replace", recording_replace)
    exit_code = run_draft(_job(source, output_dir, ai_enabled=False))

    assert exit_code == 0
    assert replacements[-1] == "result.json"
    payload = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["confirmations"] == []
    assert payload["service_requests"] == []
    assert [item["path"] for item in payload["outputs"]] == [
        str((output_dir / "moisture_summary.xlsx").resolve()),
        str((output_dir / "analysis_report.md").resolve()),
    ]
    workbook = load_workbook(output_dir / "moisture_summary.xlsx", read_only=True)
    assert workbook.sheetnames == [
        "竹丝含水率统计",
        "异常分析明细",
        "趋势分析",
        "来源追溯",
        "模型分析记录",
    ]
    workbook.close()


def test_all_failed_still_writes_schema_valid_result_and_returns_zero(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.xlsx"
    source.write_bytes(b"not a workbook")
    output_dir = tmp_path / "output"

    exit_code = run_draft(_job(source, output_dir))

    assert exit_code == 0
    payload = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["outputs"] == []
    assert payload["summary"]["failed_count"] == 1

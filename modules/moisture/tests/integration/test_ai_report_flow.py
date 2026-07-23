from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.adapters.history.repository import HistoryRepository
from moisture.application.draft_orchestrator import run_draft
from moisture.application.finalize_orchestrator import run_finalize
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode
from moisture.infrastructure.hashing import sha256_file

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _summary(tmp_path: Path, workbook_factory) -> Path:
    source = workbook_factory(
        tmp_path / "raw.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        supplier="Synthetic Supplier",
        arrival_date="2026-07-01",
        test_date="2026-07-02",
    )
    output = tmp_path / "summary-output"
    job = JobRequest(
        "1.0",
        "summary-root",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (source,),
        output,
    )
    assert run_draft(job) == 0
    return output / "moisture_summary.xlsx"


def _config(
    path: Path,
    *,
    history_ids: list[str] | None = None,
    experiences: list[dict[str, str]] | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "operation": "ai_report",
                "inputs": [{"role": "current_summary", "input_index": 0}],
                "history_ids": history_ids or [],
                "experience_selections": experiences or [],
                "question": "Compare the current period and suggest manual review steps.",
            }
        ),
        encoding="utf-8",
    )
    return path


def _job(
    summary: Path,
    config: Path,
    output: Path,
    *,
    phase: JobPhase,
    service_response: Path | None = None,
) -> JobRequest:
    return JobRequest(
        "1.0",
        "ai-report-root" if phase is JobPhase.DRAFT else "ai-report-final",
        ModuleId.MOISTURE,
        phase,
        RunMode.SINGLE,
        (summary,),
        output,
        parent_job_id="ai-report-root" if phase is JobPhase.FINALIZE else None,
        module_config_file=config,
        service_response_file=service_response,
    )


def _envelope(path: Path, request: dict[str, object], *, status: str, text=None) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task_id": "ai-report-root",
                "module_id": "moisture",
                "responses": [
                    {
                        "request_id": request["request_id"],
                        "service": "ai",
                        "status": status,
                        "text": text,
                        "error": None if status == "ok" else "provider unavailable",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_ai_report_draft_is_stable_consent_gated_and_redacted(
    tmp_path: Path, workbook_factory
) -> None:
    summary = _summary(tmp_path, workbook_factory)
    config = _config(tmp_path / "ai-config.json")
    before = sha256_file(summary)

    request_ids = []
    for name in ("draft-a", "draft-b"):
        output = tmp_path / name
        assert run_draft(_job(summary, config, output, phase=JobPhase.DRAFT)) == 0
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        assert result["status"] == "success"
        assert result["outputs"] == []
        assert len(result["service_requests"]) == 1
        request = result["service_requests"][0]
        assert request["service"] == "ai"
        assert request["requires_user_consent"] is True
        request_ids.append(request["request_id"])
        serialized = json.dumps(request, ensure_ascii=False)
        assert str(summary.parent) not in serialized
        assert "Synthetic Supplier" not in serialized
    assert request_ids[0] == request_ids[1]
    assert sha256_file(summary) == before


def test_valid_ai_response_creates_independent_markdown_and_json(
    tmp_path: Path, workbook_factory
) -> None:
    summary = _summary(tmp_path, workbook_factory)
    config = _config(tmp_path / "ai-config.json")
    draft_dir = tmp_path / "draft"
    assert run_draft(_job(summary, config, draft_dir, phase=JobPhase.DRAFT)) == 0
    draft_result = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    request = draft_result["service_requests"][0]
    response = {
        "schema_version": "1.0",
        "context_hash": request["payload"]["context_hash"],
        "overall_summary": "The current period is stable.",
        "historical_comparison": "No history was selected.",
        "review_batches": [],
        "possible_causes": ["No specific cause is asserted."],
        "recommendations": ["Continue routine manual verification."],
        "evidence_refs": [],
        "disclaimer": (
            "\u672c\u62a5\u544a\u4ec5\u4f5c\u8f85\u52a9\u5206\u6790\uff0c"
            "\u4e0d\u6784\u6210\u6b63\u5f0f\u8d28\u91cf\u7ed3\u8bba\u3002"
        ),
    }
    response_file = _envelope(
        tmp_path / "response.json", request, status="ok", text=json.dumps(response)
    )
    before = sha256_file(summary)
    final_dir = tmp_path / "final"

    assert (
        run_finalize(
            _job(
                summary,
                config,
                final_dir,
                phase=JobPhase.FINALIZE,
                service_response=response_file,
            )
        )
        == 0
    )
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))
    analysis = json.loads((final_dir / "ai_analysis_result.json").read_text(encoding="utf-8"))
    assert result["job_id"] == "ai-report-final"
    assert result["confirmations"] == [] and result["service_requests"] == []
    assert {Path(item["path"]).name for item in result["outputs"]} == {
        "ai_analysis_report.md",
        "ai_analysis_result.json",
    }
    assert analysis["status"] == "success"
    assert analysis["report_file"] == "ai_analysis_report.md"
    assert "The current period is stable." in (final_dir / "ai_analysis_report.md").read_text(
        encoding="utf-8"
    )
    assert sha256_file(summary) == before


@pytest.mark.parametrize(
    ("provider_status", "text", "expected"),
    [
        ("denied", None, "denied"),
        ("error", None, "error"),
        ("timeout", None, "timeout"),
        ("ok", "not-json", "invalid_response"),
    ],
)
def test_provider_failure_and_invalid_response_degrade_without_fake_report(
    tmp_path: Path,
    workbook_factory,
    provider_status: str,
    text: str | None,
    expected: str,
) -> None:
    summary = _summary(tmp_path, workbook_factory)
    config = _config(tmp_path / "ai-config.json")
    draft_dir = tmp_path / "draft"
    assert run_draft(_job(summary, config, draft_dir, phase=JobPhase.DRAFT)) == 0
    request = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))[
        "service_requests"
    ][0]
    response_file = _envelope(
        tmp_path / "response.json", request, status=provider_status, text=text
    )
    final_dir = tmp_path / "final"
    assert (
        run_finalize(
            _job(
                summary,
                config,
                final_dir,
                phase=JobPhase.FINALIZE,
                service_response=response_file,
            )
        )
        == 0
    )
    result = json.loads((final_dir / "ai_analysis_result.json").read_text(encoding="utf-8"))
    assert result["status"] == expected
    assert result["report_file"] is None
    assert result["degradation_reason"]
    assert not (final_dir / "ai_analysis_report.md").exists()


def test_selected_history_and_approved_experience_enter_bounded_context(
    tmp_path: Path, workbook_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = _summary(tmp_path, workbook_factory)
    data_root = tmp_path / "module-data"
    history_id = HistoryRepository(data_root / "history").import_summary(
        summary, "Synthetic history"
    )
    monkeypatch.setenv("BAMBOO_MOISTURE_DATA_DIR", str(data_root))
    experience = {
        "entry_id": "EXP-GENERIC-001",
        "version": "1.0.0",
        "sha256": "977e7e9dd5ceda8cdb81bfd4a85ca74e4a5875c535862b28476b8aeb38dfe94f",
    }
    config = _config(
        tmp_path / "ai-config.json",
        history_ids=[history_id],
        experiences=[experience],
    )
    output = tmp_path / "draft"
    assert run_draft(_job(summary, config, output, phase=JobPhase.DRAFT)) == 0
    request = json.loads((output / "result.json").read_text(encoding="utf-8"))["service_requests"][
        0
    ]
    payload = request["payload"]
    assert payload["selection_counts"]["history"] == {
        "total": 1,
        "sent": 1,
        "omitted": 0,
    }
    assert payload["selection_counts"]["experiences"] == {
        "total": 1,
        "sent": 1,
        "omitted": 0,
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(data_root) not in serialized
    assert "EXP-GENERIC-001" in serialized

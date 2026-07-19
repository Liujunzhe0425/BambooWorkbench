# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from integration.t19_helpers import valid_ai_response
from moisture.application.draft_orchestrator import _ai_request, run_draft
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.finalize_orchestrator import run_finalize
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _source(workbook_factory, path: Path) -> Path:
    return workbook_factory(
        path,
        departments={"品质": 1},
        moisture_values=(0.56,),
        mass_values=((100, 46.24, 4),),
        material_type="原竹丝",
        arrival_date="4月8日",
        test_date="4月9日",
    )


def _job(
    source: Path,
    output: Path,
    *,
    phase: JobPhase,
    confirmation: Path | None = None,
    service_response: Path | None = None,
    job_id: str | None = None,
) -> JobRequest:
    return JobRequest(
        "1.0",
        job_id or ("month-day-root" if phase is JobPhase.DRAFT else "month-day-final"),
        ModuleId.MOISTURE,
        phase,
        RunMode.SINGLE,
        (source,),
        output,
        parent_job_id="month-day-root" if phase is JobPhase.FINALIZE else None,
        confirmation_file=confirmation,
        service_response_file=service_response,
    )


def _confirmation(path: Path, confirmation_id: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "month-day-root",
                "answers": [
                    {
                        "confirmation_id": confirmation_id,
                        "value": "2026",
                        "apply_to_batch": True,
                        "remember_mapping": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _response_envelope(path: Path, response: dict[str, object]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task_id": "month-day-root",
                "module_id": "moisture",
                "responses": [response],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _draft(tmp_path: Path, source: Path) -> tuple[dict[str, object], Path]:
    output = tmp_path / "draft"
    assert run_draft(_job(source, output, phase=JobPhase.DRAFT)) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    confirmation = _confirmation(
        tmp_path / "confirmation.json",
        result["confirmations"][0]["confirmation_id"],
    )
    return result, confirmation


@pytest.mark.parametrize("status", ("ok", "denied", "error"))
def test_month_day_finalize_accepts_draft_ai_response_id(
    tmp_path: Path, workbook_factory, status: str
) -> None:
    source = _source(workbook_factory, tmp_path / "source.xlsx")
    draft, confirmation = _draft(tmp_path, source)
    request = next(item for item in draft["service_requests"] if item["service"] == "ai")
    if status == "ok":
        response = valid_ai_response(request)
    else:
        response = {
            "request_id": request["request_id"],
            "service": "ai",
            "status": status,
            "text": None,
            "error": "provider unavailable" if status == "error" else None,
        }
    response_file = _response_envelope(tmp_path / "service-response.json", response)
    output = tmp_path / f"final-{status}"

    assert (
        run_finalize(
            _job(
                source,
                output,
                phase=JobPhase.FINALIZE,
                confirmation=confirmation,
                service_response=response_file,
            )
        )
        == 0
    )
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert not any(
        marker in str(result["errors"])
        for marker in (
            "SERVICE_RESPONSE_ID_UNKNOWN",
            "SERVICE_RESPONSE_ID_MISSING",
            "service_response_invalid",
            "invalid_or_missing",
        )
    ), result["errors"]
    assert (output / "moisture_summary.xlsx").is_file()
    assert (output / "analysis_report.md").is_file()


def test_month_day_request_id_is_stable_after_year_replay(
    tmp_path: Path, workbook_factory
) -> None:
    source = _source(workbook_factory, tmp_path / "source.xlsx")
    pipeline = DeterministicPipeline(MODULE_ROOT)
    draft_job = _job(source, tmp_path / "unused", phase=JobPhase.DRAFT)

    draft = _ai_request(draft_job, pipeline.run((source,), default_year=None))
    first = _ai_request(draft_job, pipeline.run((source,), default_year=2026))
    second = _ai_request(draft_job, pipeline.run((source,), default_year=2026))

    assert draft.request is not None and first.request is not None and second.request is not None
    assert draft.request["payload"] != first.request["payload"]
    assert draft.request["request_id"] == first.request["request_id"]
    assert first.request["request_id"] == second.request["request_id"]


def test_genuinely_unknown_response_id_still_degrades_safely(
    tmp_path: Path, workbook_factory
) -> None:
    source = _source(workbook_factory, tmp_path / "source.xlsx")
    draft, confirmation = _draft(tmp_path, source)
    request = next(item for item in draft["service_requests"] if item["service"] == "ai")
    response_file = _response_envelope(
        tmp_path / "unknown-response.json",
        {
            "request_id": f"{request['request_id']}-unknown",
            "service": "ai",
            "status": "denied",
            "text": None,
        },
    )
    output = tmp_path / "unknown-final"

    assert (
        run_finalize(
            _job(
                source,
                output,
                phase=JobPhase.FINALIZE,
                confirmation=confirmation,
                service_response=response_file,
            )
        )
        == 0
    )
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert "SERVICE_RESPONSE_DEGRADED: invalid_or_missing" in result["errors"]
    assert (output / "moisture_summary.xlsx").is_file()

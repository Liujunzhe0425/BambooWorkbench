# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.draft_orchestrator import run_draft
from moisture.application.finalize_orchestrator import run_finalize
from moisture.contract.job_models import JobPhase, RunMode
from moisture.contract.monthly_snapshot import MonthlySnapshotError
from moisture.infrastructure.hashing import sha256_file
from integration.t19_helpers import (
    governed_workbook,
    job,
    pipeline,
    rule_root,
    workbook_contains_color,
    write_envelope,
)

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_summary_finalize_keeps_deterministic_color_without_ai_review(
    tmp_path: Path, workbook_factory
) -> None:
    root = rule_root(tmp_path / "module", "high")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    draft_dir = tmp_path / "draft"
    assert run_draft(job(source, draft_dir, phase=JobPhase.DRAFT), pipeline(root)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    assert not any(item["service"] == "ai" for item in draft["service_requests"])

    final_dir = tmp_path / "final"
    assert run_finalize(job(source, final_dir, phase=JobPhase.FINALIZE), pipeline(root)) == 0
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))

    assert result["job_id"] == "finalize-current"
    assert result["status"] == "success"
    assert result["confirmations"] == [] and result["service_requests"] == []
    assert workbook_contains_color(final_dir / "moisture_summary.xlsx", "orange")
    assert not workbook_contains_color(final_dir / "moisture_summary.xlsx", "red")
    assert not workbook_contains_color(final_dir / "moisture_summary.xlsx", "blue")


def test_finalize_with_period_publishes_hidden_monthly_snapshot(
    tmp_path: Path, workbook_factory
) -> None:
    root = rule_root(tmp_path / "module", "high")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    final_dir = tmp_path / "final"

    assert (
        run_finalize(
            job(
                source,
                final_dir,
                phase=JobPhase.FINALIZE,
                period=(2026, 7),
            ),
            pipeline(root),
        )
        == 0
    )

    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))
    snapshot = result["monthly_snapshot"]
    assert snapshot == {
        "schema_version": "1.0",
        "path": str((final_dir / "moisture-monthly-snapshot.json").resolve()),
        "snapshot_format": "moisture-v1",
        "year": 2026,
        "month": 7,
    }
    assert Path(snapshot["path"]).is_file()
    assert all(
        output["path"] != snapshot["path"] for output in result["outputs"]
    )


def test_finalize_preserves_sanitized_monthly_snapshot_error_code(
    tmp_path: Path,
    workbook_factory,
    monkeypatch,
) -> None:
    from moisture.application import finalize_orchestrator

    root = rule_root(tmp_path / "module", "high")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    final_dir = tmp_path / "final"

    def reject_snapshot(**_kwargs):
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_INVALID",
            r"private detail from D:\customer\source.xlsx",
        )

    monkeypatch.setattr(
        finalize_orchestrator,
        "build_monthly_snapshot",
        reject_snapshot,
    )
    assert (
        run_finalize(
            job(
                source,
                final_dir,
                phase=JobPhase.FINALIZE,
                period=(2026, 7),
            ),
            pipeline(root),
        )
        == 0
    )

    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["monthly_snapshot"] is None
    assert result["outputs"] == []
    assert result["errors"] == [
        "ARTIFACT_WRITE_FAILED: MONTHLY_SNAPSHOT_INVALID"
    ]
    assert "MonthlySnapshotError" not in json.dumps(result)
    assert "customer" not in json.dumps(result).lower()


def test_normalized_record_id_conflict_fails_without_overwriting_artifacts(
    tmp_path: Path,
    workbook_factory,
) -> None:
    root = rule_root(tmp_path / "module", "high")
    first = governed_workbook(
        workbook_factory,
        tmp_path / "same-batch.xlsx",
        "high",
    )
    second = governed_workbook(
        workbook_factory,
        tmp_path / "same-batch .xlsx",
        "low",
    )
    before = {path: sha256_file(path) for path in (first, second)}

    for order, inputs in enumerate(((first, second), (second, first)), start=1):
        final_dir = tmp_path / f"conflict-{order}"
        request = replace(
            job(
                first,
                final_dir,
                phase=JobPhase.FINALIZE,
                period=(2026, 7),
            ),
            input_files=inputs,
            run_mode=RunMode.BATCH,
        )

        assert run_finalize(request, pipeline(root)) == 0
        result = json.loads(
            (final_dir / "result.json").read_text(encoding="utf-8")
        )

        assert result["status"] == "failed"
        assert result["monthly_snapshot"] is None
        assert result["outputs"] == []
        assert result["errors"] == [
            "ARTIFACT_WRITE_FAILED: MONTHLY_SNAPSHOT_RECORD_ID_CONFLICT"
        ]
        assert not (final_dir / "moisture-monthly-snapshot.json").exists()
        assert not (final_dir / "moisture_summary.xlsx").exists()
        assert not (final_dir / "analysis_report.md").exists()

    assert {path: sha256_file(path) for path in (first, second)} == before


class _KnowledgePipeline:
    def __init__(self, delegate) -> None:
        self.delegate = delegate

    def run(self, input_files, *, default_year=None):
        outcome = self.delegate.run(input_files, default_year=default_year)
        values = {field: getattr(outcome, field) for field in outcome.__dataclass_fields__}
        values["knowledge_guidance_needed"] = True
        return SimpleNamespace(**values)


def test_valid_knowledge_response_remains_report_only_guidance(
    tmp_path: Path, workbook_factory
) -> None:
    root = rule_root(tmp_path / "module", "high")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    governed = _KnowledgePipeline(pipeline(root))
    draft_dir = tmp_path / "draft"
    draft_job = job(source, draft_dir, phase=JobPhase.DRAFT, allowed_scopes=("moisture",))
    assert run_draft(draft_job, governed) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    request = next(item for item in draft["service_requests"] if item["service"] == "knowledge")
    assert not any(item["service"] == "ai" for item in draft["service_requests"])
    response_file = write_envelope(
        tmp_path / "service-response.json",
        [
            {
                "request_id": request["request_id"],
                "service": "knowledge",
                "status": "ok",
                "items": [
                    {
                        "record_id": "KN-001",
                        "namespace": "moisture",
                        "title": "复核指引",
                        "content": "检查原始称重记录。",
                        "source_kind": "local_document",
                        "source_path": r"C:\private\guidance.md",
                    }
                ],
            }
        ],
    )

    final_dir = tmp_path / "final"
    final_job = job(
        source,
        final_dir,
        phase=JobPhase.FINALIZE,
        service_file=response_file,
        allowed_scopes=("moisture",),
    )
    assert run_finalize(final_job, governed) == 0
    report = (final_dir / "analysis_report.md").read_text(encoding="utf-8")

    assert "Knowledge `moisture/KN-001`" in report
    assert "C:\\private" not in report
    assert workbook_contains_color(final_dir / "moisture_summary.xlsx", "orange")

from datetime import UTC, datetime
from pathlib import Path

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.result import ModuleResult, OutputArtifact, ResultSummary
from core.tasks.output_publisher import publish_outputs


def test_publishes_task_outputs_to_numbered_isolated_folder(tmp_path: Path) -> None:
    task_dir = tmp_path / "tasks" / "job-123456"
    output_dir = task_dir / "output-final"
    output_dir.mkdir(parents=True)
    report = output_dir / "分析报告.md"
    report.write_text("ok", encoding="utf-8")
    (output_dir / "result.json").write_text("{}", encoding="utf-8")
    now = datetime(2026, 7, 22, 14, 30, 15, tzinfo=UTC)
    result = ModuleResult(
        schema_version="1.0",
        job_id="job-123456",
        module_id=ModuleId.MOISTURE,
        module_version="1.0.0",
        status=TaskStatus.SUCCESS,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            anomaly_count=0,
            confirmation_count=0,
        ),
        outputs=[
            OutputArtifact(
                type="analysis",
                path=str(report),
                label="分析报告",
                mime_type="text/markdown",
            )
        ],
        started_at=now,
        finished_at=now,
    )
    external = tmp_path / "customer-output"

    published = publish_outputs(
        result,
        task_number=123,
        task_dir=task_dir,
        task_output_dir=output_dir,
        configured_root=str(external),
    )

    folder = external / "000123-竹丝水分-20260722-223015"
    assert Path(published.outputs[0].path) == folder / "分析报告.md"
    assert Path(published.outputs[0].path).read_text(encoding="utf-8") == "ok"
    assert (folder / "result.json").is_file()
    assert report.is_file()


def test_empty_output_setting_keeps_internal_paths(tmp_path: Path) -> None:
    task_dir = tmp_path / "tasks" / "job-123456"
    output_dir = task_dir / "output-final"
    output_dir.mkdir(parents=True)
    report = output_dir / "report.md"
    report.write_text("ok", encoding="utf-8")
    now = datetime.now(UTC)
    result = ModuleResult(
        schema_version="1.0",
        job_id="job-123456",
        module_id=ModuleId.BOILING,
        module_version="1.0.0",
        status=TaskStatus.SUCCESS,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            anomaly_count=0,
            confirmation_count=0,
        ),
        outputs=[
            OutputArtifact(
                type="report",
                path=str(report),
                label="报告",
                mime_type="text/markdown",
            )
        ],
        started_at=now,
        finished_at=now,
    )

    assert publish_outputs(
        result,
        task_number=1,
        task_dir=task_dir,
        task_output_dir=output_dir,
        configured_root="",
    ) is result


def test_existing_folder_name_gets_suffix_instead_of_overwrite(tmp_path: Path) -> None:
    task_dir = tmp_path / "tasks" / "job-123456"
    output_dir = task_dir / "output-final"
    output_dir.mkdir(parents=True)
    report = output_dir / "report.md"
    report.write_text("new", encoding="utf-8")
    now = datetime(2026, 7, 22, 14, 30, 15, tzinfo=UTC)
    result = ModuleResult(
        schema_version="1.0",
        job_id="job-123456",
        module_id=ModuleId.MOISTURE,
        module_version="1.0.0",
        status=TaskStatus.SUCCESS,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            anomaly_count=0,
            confirmation_count=0,
        ),
        outputs=[
            OutputArtifact(
                type="report",
                path=str(report),
                label="报告",
                mime_type="text/markdown",
            )
        ],
        started_at=now,
        finished_at=now,
    )
    external = tmp_path / "customer-output"
    existing = external / "000001-竹丝水分-20260722-223015"
    existing.mkdir(parents=True)
    marker = existing / "keep.txt"
    marker.write_text("old", encoding="utf-8")

    published = publish_outputs(
        result,
        task_number=1,
        task_dir=task_dir,
        task_output_dir=output_dir,
        configured_root=str(external),
    )

    assert marker.read_text(encoding="utf-8") == "old"
    assert Path(published.outputs[0].path).parent.name.endswith("-2")

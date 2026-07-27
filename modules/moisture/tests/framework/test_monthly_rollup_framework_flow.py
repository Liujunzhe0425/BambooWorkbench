# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtTest import QSignalSpy

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "modules" / "moisture"
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from app.bootstrap import build_context
from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.enums import ModuleId

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_real_framework_finalize_snapshot_and_offline_rollup(
    qtbot,
    tmp_path: Path,
    workbook_factory,
) -> None:
    context = build_context(tmp_path / "app-data", use_mocks=False)
    try:
        module = context.registry.get(ModuleId.MOISTURE)
        assert module.manifest.module_version == "1.3.2"
        assert "monthly_rollup" in module.manifest.capabilities
        assert module.manifest.monthly_rollup is not None

        source_stem = "001-4.10供应商甲原竹丝水分检测（2） "
        record_id = source_stem.strip()
        source = workbook_factory(
            tmp_path / f"{source_stem}.xlsx",
            moisture_values=(0.50,),
            mass_values=((100, 50, 0),),
            arrival_date="4.8",
            test_date="4.9",
        )
        needs_confirmation = QSignalSpy(context.task_service.needs_confirmation)
        finished = QSignalSpy(context.task_service.finished)
        failed = QSignalSpy(context.task_service.failed)
        job_id = context.task_service.create_and_start(
            ModuleId.MOISTURE,
            [source],
            task_name="moisture-2026-04",
            period_year=2026,
            period_month=4,
        )
        qtbot.waitUntil(
            lambda: needs_confirmation.count() + failed.count() == 1,
            timeout=60_000,
        )
        assert failed.count() == 0, failed.at(0) if failed.count() else None

        task_dir = context.paths.tasks / job_id
        draft = json.loads(
            (task_dir / "output-draft" / "result.json").read_text(encoding="utf-8")
        )
        prompt = draft["confirmations"][0]
        assert prompt["field"] == "default_year"

        bundle = context.confirmation_service.submit(
            job_id,
            [
                ConfirmationAnswer(
                    confirmation_id=prompt["confirmation_id"],
                    value="2026",
                    apply_to_batch=True,
                    remember_mapping=False,
                )
            ],
        )
        context.task_service.finalize(job_id, bundle)
        qtbot.waitUntil(
            lambda: finished.count() + failed.count() == 1,
            timeout=120_000,
        )

        assert failed.count() == 0, failed.at(0) if failed.count() else None
        final = json.loads(
            (task_dir / "output-final" / "result.json").read_text(encoding="utf-8")
        )
        assert final["job_id"] == job_id
        assert final["confirmations"] == []
        assert final["service_requests"] == []
        assert final["monthly_snapshot"]["year"] == 2026
        assert final["monthly_snapshot"]["month"] == 4
        assert Path(final["monthly_snapshot"]["path"]).is_file()
        snapshot_payload = json.loads(
            Path(final["monthly_snapshot"]["path"]).read_text(encoding="utf-8")
        )
        assert [item["record_id"] for item in snapshot_payload["records"]] == [
            record_id
        ]
        assert all(
            output["path"] != final["monthly_snapshot"]["path"]
            for output in final["outputs"]
        )

        slot = context.monthly_repository.get_slot("moisture", 2026, 4)
        assert slot is not None
        assert slot["official_job_id"] == job_id
        task = context.task_repository.get(job_id)
        assert task["status"] == "success"
        registered_outputs = context.task_repository.list_outputs(job_id)
        output_names = {Path(str(item["path"])).name for item in registered_outputs}
        assert output_names == {
            "moisture_summary.xlsx",
            "analysis_report.md",
            "moisture_business_records.json",
        }
        business_path = next(
            Path(str(item["path"]))
            for item in registered_outputs
            if Path(str(item["path"])).name == "moisture_business_records.json"
        )
        business = json.loads(business_path.read_text(encoding="utf-8"))
        assert [item["record_id"] for item in business["records"]] == [record_id]
        assert source.name == f"{source_stem}.xlsx"
    finally:
        context.close()

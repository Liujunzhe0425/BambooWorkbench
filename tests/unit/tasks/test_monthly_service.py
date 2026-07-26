import hashlib
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.manifest import ModuleManifest
from core.contracts.monthly import (
    MonthlyRollupRequest,
    MonthlyRollupResult,
    RollupOutputArtifact,
    RollupSnapshotHash,
)
from core.contracts.result import ModuleResult, MonthlySnapshotArtifact, ResultSummary
from core.knowledge.learning import LearningEvidenceRepository
from core.modules.registry import RegisteredModule
from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.monthly import MonthlyRepository
from core.storage.repositories.output_roots import OutputRootRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.monthly_service import MonthlyRollupService


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Registry:
    def __init__(self, module: RegisteredModule) -> None:
        self.module = module

    def get(self, _module_id: ModuleId) -> RegisteredModule:
        return self.module


class _SuccessfulRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    seen_requests: list[MonthlyRollupRequest] = []

    def start(self, _module: RegisteredModule, request_path: Path) -> None:
        request = MonthlyRollupRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        self.seen_requests.append(request)
        snapshot_root = Path(request.snapshot_root).resolve()
        assert all(
            Path(item.path).resolve().is_relative_to(snapshot_root)
            for item in request.snapshots
        )
        artifact = Path(request.output_dir) / "moisture_summary.xlsx"
        artifact.write_bytes(b"xlsx")
        self.completed.emit(
            MonthlyRollupResult(
                schema_version="1.0",
                transaction_id=request.transaction_id,
                module_id=request.module_id,
                module_version=request.module_version,
                year=request.year,
                target_month=request.target_month,
                status="success",
                used_months=[item.month for item in request.snapshots],
                snapshot_hashes=[
                    RollupSnapshotHash(
                        snapshot_id=item.snapshot_id,
                        month=item.month,
                        sha256=item.sha256,
                    )
                    for item in request.snapshots
                ],
                record_count=1,
                outputs=[
                    RollupOutputArtifact(
                        type="excel",
                        path=str(artifact),
                        label="累计表",
                        mime_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                        sha256=_sha256(artifact),
                    )
                ],
                network_call_count=0,
            )
        )

    def shutdown(self) -> bool:
        return True


def test_monthly_service_uses_authorized_snapshot_root_and_commits(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path / "app-data")
    database = Database.open(paths)
    database.migrate()
    tasks = TaskRepository(database)
    confirmations = ConfirmationRepository(database)
    monthly = MonthlyRepository(database)
    learning = LearningEvidenceRepository(database)
    roots = OutputRootRepository(database, paths)
    roots.initialize_default()
    module_root = tmp_path / "module"
    module_root.mkdir()
    manifest = ModuleManifest.model_validate(
        {
            "schema_version": "1.0",
            "module_id": "moisture",
            "module_name": "竹丝水分",
            "module_version": "1.3.0",
            "entrypoint": "run_module.bat",
            "capabilities": ["monthly_rollup"],
            "monthly_rollup": {
                "schema_version": "1.0",
                "entrypoint": "run_module.bat",
                "snapshot_schema": "schemas/snapshot.json",
                "request_schema": "schemas/request.json",
                "response_schema": "schemas/response.json",
            },
            "supported_extensions": [".xlsx"],
            "supports_single_file": True,
            "supports_batch": True,
            "supports_incremental": False,
            "requires_network": False,
        }
    )
    registered = RegisteredModule(manifest, module_root, False, "healthy")
    job_id = "job-monthly-001"
    now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
    tasks.create(
        job_id,
        "moisture",
        "running_finalize",
        now.isoformat(),
        task_name="竹丝水分-2026年03月",
        period_year=2026,
        period_month=3,
        output_root_id=int(roots.current()["id"]),
    )
    output_final = paths.tasks / job_id / "output-final"
    output_final.mkdir(parents=True)
    source_snapshot = output_final / "moisture-monthly-snapshot.json"
    source_snapshot.write_text('{"records":[]}', encoding="utf-8")
    result = ModuleResult(
        schema_version="1.0",
        job_id=job_id,
        module_id=ModuleId.MOISTURE,
        module_version="1.3.0",
        status=TaskStatus.SUCCESS,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            anomaly_count=0,
            confirmation_count=0,
        ),
        monthly_snapshot=MonthlySnapshotArtifact(
            schema_version="1.0",
            path=str(source_snapshot),
            snapshot_format="moisture-v1",
            year=2026,
            month=3,
        ),
        started_at=now,
        finished_at=now,
    )
    _SuccessfulRunner.seen_requests.clear()
    service = MonthlyRollupService(
        paths,
        _Registry(registered),
        tasks,
        confirmations,
        monthly,
        learning,
        roots,
        runner_factory=_SuccessfulRunner,
    )
    completed: list[ModuleResult] = []
    service.completed.connect(lambda _job_id, completed_result: completed.append(completed_result))

    service.start(job_id, result)

    assert completed
    assert len(_SuccessfulRunner.seen_requests) == 1
    request = _SuccessfulRunner.seen_requests[0]
    assert Path(request.snapshots[0].path).parent == Path(request.snapshot_root)
    assert monthly.get_slot("moisture", 2026, 3)["official_job_id"] == job_id
    published = tasks.list_outputs(job_id)
    assert len(published) == 1
    assert Path(str(published[0]["path"])).is_file()
    database.close()

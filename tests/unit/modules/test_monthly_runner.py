import hashlib
import json
from pathlib import Path

import pytest

from core.contracts.enums import ModuleId
from core.contracts.manifest import ModuleManifest
from core.contracts.monthly import (
    MonthlyRollupRequest,
    MonthlyRollupResult,
    RollupOutputArtifact,
    RollupSnapshotHash,
    RollupSnapshotRef,
)
from core.modules.monthly_runner import MonthlyRollupRunner, _offline_environment
from core.modules.registry import RegisteredModule


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runner_fixture(tmp_path: Path) -> tuple[MonthlyRollupRunner, Path, Path]:
    module = tmp_path / "module"
    schemas = module / "schemas"
    schemas.mkdir(parents=True)
    (module / "run_module.bat").write_text("@exit /b 0\n", encoding="utf-8")
    (schemas / "response.json").write_text(
        json.dumps(MonthlyRollupResult.model_json_schema()), encoding="utf-8"
    )
    for name in ("snapshot.json", "request.json"):
        (schemas / name).write_text("{}", encoding="utf-8")
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
    snapshot_root = tmp_path / "authorized-snapshots"
    snapshot_root.mkdir()
    snapshot = snapshot_root / "03-snapshot.json"
    snapshot.write_text('{"records":[]}', encoding="utf-8")
    output = tmp_path / "staged-output"
    output.mkdir()
    request = MonthlyRollupRequest(
        schema_version="1.0",
        transaction_id="transaction-001",
        module_id=ModuleId.MOISTURE,
        module_version="1.3.0",
        year=2026,
        target_month=3,
        snapshots=[
            RollupSnapshotRef(
                snapshot_id="snapshot-001",
                job_id="job-123456",
                module_id=ModuleId.MOISTURE,
                year=2026,
                month=3,
                path=str(snapshot),
                size=snapshot.stat().st_size,
                sha256=_sha256(snapshot),
            )
        ],
        snapshot_root=str(snapshot_root),
        output_dir=str(output),
        offline_required=True,
    )
    runner = MonthlyRollupRunner()
    runner._request = request
    runner._module = RegisteredModule(manifest, module, False, "healthy")
    return runner, snapshot, output


def test_monthly_runner_validates_snapshot_and_output_hashes(tmp_path: Path) -> None:
    runner, snapshot, output = _runner_fixture(tmp_path)
    artifact = output / "report.md"
    artifact.write_text("ok", encoding="utf-8")
    result = MonthlyRollupResult(
        schema_version="1.0",
        transaction_id="transaction-001",
        module_id=ModuleId.MOISTURE,
        module_version="1.3.0",
        year=2026,
        target_month=3,
        status="success",
        used_months=[3],
        snapshot_hashes=[
            RollupSnapshotHash(
                snapshot_id="snapshot-001", month=3, sha256=_sha256(snapshot)
            )
        ],
        record_count=1,
        outputs=[
            RollupOutputArtifact(
                type="markdown",
                path=str(artifact),
                label="报告",
                mime_type="text/markdown",
                sha256=_sha256(artifact),
            )
        ],
        network_call_count=0,
    )
    (output / "rollup-result.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )

    MonthlyRollupRunner._validate_snapshot_integrity(runner._request)
    assert runner._load_result().record_count == 1

    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        runner._load_result()


def test_monthly_request_rejects_snapshot_outside_authorized_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="snapshot_root"):
        MonthlyRollupRequest(
            schema_version="1.0",
            transaction_id="transaction-001",
            module_id=ModuleId.MOISTURE,
            module_version="1.3.0",
            year=2026,
            target_month=3,
            snapshots=[
                RollupSnapshotRef(
                    snapshot_id="snapshot-001",
                    job_id="job-123456",
                    module_id=ModuleId.MOISTURE,
                    year=2026,
                    month=3,
                    path=str(outside),
                    size=2,
                    sha256=_sha256(outside),
                )
            ],
            snapshot_root=str(root),
            output_dir=str(tmp_path / "output"),
            offline_required=True,
        )


def test_monthly_runner_accepts_only_json_progress_lines() -> None:
    class _Process:
        def readAllStandardOutput(self) -> bytes:
            return b'{"type":"progress","percent":50,"message":"rendering"}\n'

    runner = MonthlyRollupRunner()
    process = _Process()
    runner._process = process
    runner._generation = 1
    events = []
    runner.progress.connect(events.append)

    runner._read_stdout(1, process)

    assert len(events) == 1
    assert events[0].percent == 50


def test_offline_environment_uses_qt_key_enumeration_and_removes_secrets(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BAMBOO_TEST_TOKEN", "must-not-leak")

    environment = _offline_environment()

    assert environment.value("BAMBOO_OFFLINE") == "1"
    assert not environment.contains("BAMBOO_TEST_TOKEN")
    assert environment.value("HTTP_PROXY") == "http://127.0.0.1:9"

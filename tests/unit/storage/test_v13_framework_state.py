import hashlib
from datetime import UTC, datetime
from pathlib import Path

from core.contracts.result import LearningCandidate, LearningDescriptor, OutputArtifact
from core.knowledge.learning import LearningEvidenceRepository
from core.platform.installation import complete_fresh_installation, prepare_installation
from core.platform.paths import AppPaths
from core.security.credentials import InMemoryCredentialStore
from core.storage.database import Database
from core.storage.repositories.credential_state import CredentialStateRepository
from core.storage.repositories.monthly import MonthlyRepository
from core.storage.repositories.output_roots import OutputRootRepository
from core.storage.repositories.tasks import TaskRepository
from core.storage.settings import SettingsStore
from core.tasks.output_manifest import (
    OutputManifestMetadata,
    validate_output_manifest,
    write_output_manifest,
)
from core.tasks.output_recovery import OutputRecoveryService


def _open(tmp_path: Path) -> tuple[AppPaths, Database]:
    paths = AppPaths.for_root(tmp_path)
    database = Database.open(paths)
    database.migrate()
    return paths, database


def test_monthly_commit_switches_slot_outputs_and_learning_atomically(
    tmp_path: Path,
) -> None:
    paths, database = _open(tmp_path)
    tasks = TaskRepository(database)
    monthly = MonthlyRepository(database)
    now = datetime.now(UTC).isoformat()
    tasks.create(
        "job-123456",
        "moisture",
        "running_finalize",
        now,
        task_name="竹丝水分-2026年03月",
        period_year=2026,
        period_month=3,
    )
    snapshot = paths.tasks / "job-123456" / "monthly-snapshot.json"
    snapshot.parent.mkdir()
    snapshot.write_text("{}", encoding="utf-8")
    snapshot_id = monthly.register_snapshot(
        module_id="moisture",
        year=2026,
        month=3,
        job_id="job-123456",
        contract_version="1.0",
        snapshot_format="moisture-v1",
        path=snapshot,
        size=2,
        sha256="a" * 64,
    )
    transaction_id = monthly.begin_transaction(
        module_id="moisture",
        year=2026,
        candidate_month=3,
        candidate_job_id="job-123456",
        affected_months=[3],
    )
    monthly.set_transaction_state(transaction_id, "rendering")
    monthly.validate_item(
        transaction_id,
        3,
        staged_path=tmp_path / "staging",
        manifest_sha256="b" * 64,
    )
    output = tmp_path / "output" / "report.xlsx"
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(b"xlsx")
    artifact = OutputArtifact(
        type="excel",
        path=str(output),
        label="累计表",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    monthly.commit(
        transaction_id,
        snapshot_by_month={3: snapshot_id},
        outputs_by_job={"job-123456": [artifact]},
        activate_learning_job="job-123456",
    )

    slot = monthly.get_slot("moisture", 2026, 3)
    assert slot is not None
    assert slot["official_job_id"] == "job-123456"
    assert tasks.list_outputs("job-123456")[0]["path"] == str(output)
    database.close()


def test_learning_uses_exact_level_then_backoff_and_base_suggestion_for_tie(
    tmp_path: Path,
) -> None:
    _paths, database = _open(tmp_path)
    tasks = TaskRepository(database)
    learning = LearningEvidenceRepository(database)
    descriptor = LearningDescriptor(
        schema_version="1.0",
        learning_key="factory-choice",
        field="责任工厂",
        context={"product_category": "户外板", "issue_type": "开裂"},
        context_levels=[
            ["product_category", "issue_type"],
            ["product_category"],
        ],
        candidates=[
            LearningCandidate(candidate_id="a", label="一厂"),
            LearningCandidate(candidate_id="b", label="二厂"),
        ],
        base_suggestion_id="a",
    )
    for index, candidate in enumerate(("b", "a", "b"), 1):
        job_id = f"job-{index:06d}"
        tasks.create(
            job_id,
            "after_sales",
            "success",
            datetime.now(UTC).isoformat(),
            task_name="售后分析-2026年03月",
            period_year=2026,
            period_month=3,
        )
        selected = descriptor
        if index > 1:
            selected = descriptor.model_copy(
                update={
                    "context": {
                        "product_category": "户外板",
                        "issue_type": "变色",
                    }
                }
            )
        learning.stage(
            job_id=job_id,
            module_id="after_sales",
            year=2026,
            month=3,
            confirmation_id=f"confirmation-{index}",
            descriptor=selected,
            candidate_id=candidate,
        )
        learning.activate_for_job(job_id)

    match = learning.preference("after_sales", descriptor)

    assert match is not None
    assert match.candidate_id == "b"
    assert match.context_fields == ("product_category", "issue_type")
    assert learning.preference("moisture", descriptor) is None
    database.close()


def test_output_manifest_uses_relative_paths_and_detects_tampering(tmp_path: Path) -> None:
    result_dir = tmp_path / "output" / "竹丝水分-20260726-120000"
    nested = result_dir / "reports" / "analysis.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("ok", encoding="utf-8")
    artifact = OutputArtifact(
        type="report",
        path=str(nested),
        label="分析报告",
        mime_type="text/markdown",
    )
    metadata = OutputManifestMetadata(
        installation_id="instance-1",
        job_id="job-123456",
        task_name="竹丝水分-2026年03月",
        module_id="moisture",
        year=2026,
        month=3,
        created_at="2026-03-01T00:00:00+08:00",
        completed_at="2026-03-01T00:01:00+08:00",
        committed_at="2026-03-01T00:01:01+08:00",
        snapshot_format="moisture-v1",
        snapshot_sha256="a" * 64,
    )
    manifest = write_output_manifest(result_dir, metadata, [artifact])

    payload = validate_output_manifest(manifest)

    assert payload["outputs"][0]["path"] == "reports/analysis.md"
    assert str(tmp_path) not in manifest.read_text(encoding="utf-8")
    manifest.chmod(0o666)
    nested.write_text("tampered", encoding="utf-8")
    try:
        validate_output_manifest(manifest)
    except ValueError as error:
        assert "integrity" in str(error)
    else:
        raise AssertionError("tampered output must be rejected")


def test_credential_verification_is_bound_to_exact_revision_and_configuration(
    tmp_path: Path,
) -> None:
    _paths, database = _open(tmp_path)
    state = CredentialStateRepository(database)
    first = state.rotate_revision("deepseek")
    state.mark_verified("deepseek", "https://api.deepseek.com", "deepseek-chat")
    assert state.is_verified(
        "deepseek", "https://api.deepseek.com", "deepseek-chat"
    )
    assert not state.is_verified("deepseek", "https://api.deepseek.com", "other")
    assert state.rotate_revision("deepseek") != first
    assert not state.is_verified(
        "deepseek", "https://api.deepseek.com", "deepseek-chat"
    )
    database.close()


def test_fresh_install_reset_preserves_source_output_but_clears_internal_state(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "install")
    paths.ensure()
    source = paths.source / "竹丝水分" / "source.xlsx"
    output = paths.output / "result.xlsx"
    source.write_bytes(b"source")
    output.write_bytes(b"result")
    paths.database.write_bytes(b"stale-db")
    stale_task = paths.tasks / "stale.txt"
    stale_task.write_text("stale", encoding="utf-8")

    state = prepare_installation(paths)
    database = Database.open(paths)
    database.migrate()
    complete_fresh_installation(
        paths,
        state,
        SettingsStore(database),
        InMemoryCredentialStore(),
    )

    assert source.read_bytes() == b"source"
    assert output.read_bytes() == b"result"
    assert not stale_task.exists()
    assert database.scalar("SELECT version FROM schema_version") == 5
    database.close()


def test_database_loss_recovers_official_month_from_manifest_and_internal_snapshot(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "recover-install")
    state = prepare_installation(paths)
    first = Database.open(paths)
    first.migrate()
    complete_fresh_installation(
        paths, state, SettingsStore(first), InMemoryCredentialStore()
    )
    task_id = "job-recover-001"
    snapshot = paths.tasks / task_id / "monthly-snapshot.json"
    snapshot.parent.mkdir()
    snapshot.write_text('{"records":[]}', encoding="utf-8")
    snapshot_digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    result_dir = paths.output / "竹丝水分-20260301-120000"
    artifact_path = result_dir / "累计.xlsx"
    result_dir.mkdir()
    artifact_path.write_bytes(b"xlsx")
    artifact = OutputArtifact(
        type="excel",
        path=str(artifact_path),
        label="累计表",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    write_output_manifest(
        result_dir,
        OutputManifestMetadata(
            installation_id=state.instance_id,
            job_id=task_id,
            task_name="竹丝水分-2026年03月",
            module_id="moisture",
            year=2026,
            month=3,
            created_at="2026-03-01T12:00:00+08:00",
            completed_at="2026-03-01T12:01:00+08:00",
            committed_at="2026-03-01T12:01:01+08:00",
            snapshot_format="moisture-v1",
            snapshot_sha256=snapshot_digest,
            transaction_id="transaction-recover-001",
        ),
        [artifact],
    )
    first.close()
    paths.database.unlink()

    recovered_db = Database.open(paths)
    recovered_db.migrate()
    tasks = TaskRepository(recovered_db)
    monthly = MonthlyRepository(recovered_db)
    roots = OutputRootRepository(recovered_db, paths)
    roots.initialize_default()
    summary = OutputRecoveryService(paths, tasks, monthly, roots).scan()

    assert summary["recovered"] == 1, summary
    assert tasks.get(task_id)["result_integrity"] == "ok"
    assert monthly.get_slot("moisture", 2026, 3)["official_job_id"] == task_id
    recovered_db.close()

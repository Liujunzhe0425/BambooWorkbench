import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.local_approved_repository import (  # noqa: E402
    LocalApprovedExperienceRepository,
)
from moisture.adapters.experience.local_editable_repository import (  # noqa: E402
    ExperienceAdminConflictError,
    ExperienceAdminSecurityError,
    ExperienceAdminValidationError,
    LocalEditableExperienceRepository,
)
from moisture.ports.experience_repository import ExperienceQuery  # noqa: E402

NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _document(*, version: str = "1.0.0", status: str = "draft", body: str = "指导") -> str:
    payload = {
        "experience_id": "EXP-001",
        "version": version,
        "status": status,
        "title": "竹丝复核指导",
        "source": "governed/local",
        "applicable_suppliers": ["供应方"],
        "applicable_materials": ["原竹丝"],
        "applicable_seasons": ["summer"],
        "applicable_metrics": ["total_average"],
        "author": "author-a",
        "reviewer": "reviewer-b",
        "evidence_sources": ["evidence/1"],
        "effective_at": "2026-01-01T00:00:00Z",
        "supersedes": None if version == "1.0.0" else "1.0.0",
    }
    return f"---\n{yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)}---\n{body}\n"


def _runtime_query() -> ExperienceQuery:
    return ExperienceQuery(
        supplier="供应方",
        material="原竹丝",
        season="summer",
        metric="total_average",
        as_of=NOW,
    )


def test_create_update_and_hash_conflict(tmp_path: Path) -> None:
    repository = LocalEditableExperienceRepository(tmp_path)
    created = repository.create(_document())
    updated = repository.update("EXP-001", "1.0.0", _document(body="修改"), created.sha256)
    assert updated.sha256 != created.sha256
    assert repository.show("EXP-001", "1.0.0").body == "修改"
    with pytest.raises(ExperienceAdminConflictError, match="hash"):
        repository.update("EXP-001", "1.0.0", _document(body="冲突"), created.sha256)


def test_invalid_schema_path_and_id_version_conflicts(tmp_path: Path) -> None:
    repository = LocalEditableExperienceRepository(tmp_path)
    with pytest.raises(ExperienceAdminValidationError):
        repository.create("---\nstatus: draft\n---\nbad")
    with pytest.raises(ExperienceAdminSecurityError):
        repository.show("../escape", "1.0.0")
    repository.create(_document())
    with pytest.raises(ExperienceAdminConflictError):
        repository.create(_document())


def test_linked_lifecycle_entry_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalEditableExperienceRepository(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text(_document(), encoding="utf-8")
    link = tmp_path / "draft" / "linked.md"
    try:
        link.symlink_to(outside)
    except OSError:
        link.write_text(_document(), encoding="utf-8")
        original = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == link or original(path),
        )
    with pytest.raises(ExperienceAdminSecurityError):
        repository.list()


def test_publish_runtime_visibility_new_version_and_retire_history(tmp_path: Path) -> None:
    repository = LocalEditableExperienceRepository(tmp_path)
    draft = repository.create(_document())
    runtime = LocalApprovedExperienceRepository(tmp_path, as_of=NOW)
    assert runtime.search(_runtime_query()) == []

    approved = repository.publish("EXP-001", "1.0.0", draft.sha256)
    assert [item.version for item in runtime.search(_runtime_query())] == ["1.0.0"]
    with pytest.raises(ExperienceAdminConflictError, match="approved"):
        repository.update("EXP-001", "1.0.0", _document(body="illegal"), approved.sha256)

    next_draft = repository.create(_document(version="2.0.0"))
    assert next_draft.version == "2.0.0"
    retired = repository.retire("EXP-001", "1.0.0", approved.sha256)
    assert retired.status == "retired"
    assert repository.show("EXP-001", "1.0.0").status == "retired"
    assert runtime.search(_runtime_query()) == []
    assert any((tmp_path / "retired").glob("*.md"))


def test_atomic_failure_preserves_old_file_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalEditableExperienceRepository(tmp_path)
    draft = repository.create(_document())
    old = repository.show("EXP-001", "1.0.0")
    original_replace = __import__("os").replace

    def fail_replace(source: object, target: object) -> None:
        if Path(target).name == "manifest.json":
            raise OSError("simulated")
        original_replace(source, target)

    monkeypatch.setattr(
        "moisture.adapters.experience.local_editable_repository.os.replace", fail_replace
    )
    with pytest.raises(OSError):
        repository.publish("EXP-001", "1.0.0", draft.sha256)
    assert repository.show("EXP-001", "1.0.0") == old
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entries"] == []
    assert not list((tmp_path / "approved").glob("*.md"))


def test_list_validate_and_content_hash(tmp_path: Path) -> None:
    repository = LocalEditableExperienceRepository(tmp_path)
    validated = repository.validate(_document())
    created = repository.create(_document())
    assert validated.experience_id == "EXP-001"
    assert repository.list() == [created]
    path = next((tmp_path / "draft").glob("*.md"))
    assert created.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_show_and_retire_support_existing_noncanonical_approved_filename(
    tmp_path: Path,
) -> None:
    approved = tmp_path / "approved"
    approved.mkdir(parents=True)
    content = _document(status="approved").encode()
    existing = approved / "legacy-name.md"
    existing.write_bytes(content)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "path": "approved/legacy-name.md",
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    repository = LocalEditableExperienceRepository(tmp_path)
    shown = repository.show("EXP-001", "1.0.0")
    retired = repository.retire("EXP-001", "1.0.0", shown.sha256)
    assert retired.status == "retired"
    assert not existing.exists()

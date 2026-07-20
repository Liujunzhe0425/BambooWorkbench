import hashlib
import inspect
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.local_approved_repository import (  # noqa: E402
    ExperienceConflictError,
    ExperienceSecurityError,
    ExperienceValidationError,
    LocalApprovedExperienceRepository,
)
from moisture.ports.experience_repository import (  # noqa: E402
    ExperienceQuery,
    ExperienceRepository,
)

NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _metadata(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "experience_id": "EXP-001",
        "version": "1.0.0",
        "status": "approved",
        "title": "竹丝季节复核指导",
        "source": "internal-review/EXP-001",
        "applicable_suppliers": ["示例供应方"],
        "applicable_materials": ["原竹丝"],
        "applicable_seasons": ["spring"],
        "applicable_metrics": ["total_average"],
        "author": "author-a",
        "reviewer": "reviewer-b",
        "evidence_sources": ["internal-evidence/EXP-001"],
        "effective_at": "2026-01-01T00:00:00Z",
        "supersedes": None,
    }
    value.update(updates)
    return value


def _write_entry(
    root: Path,
    *,
    filename: str = "entry.md",
    body: str = "复核近期来料与烘干记录。",
    include: bool = True,
    **updates: object,
) -> Path:
    approved = root / "approved"
    approved.mkdir(parents=True, exist_ok=True)
    payload = _metadata(**updates)
    path = approved / filename
    path.write_text(
        f"---\n{yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)}---\n{body}\n",
        encoding="utf-8",
    )
    entries = []
    manifest = root / "manifest.json"
    if manifest.exists():
        entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    if include:
        entries.append(
            {
                "path": f"approved/{filename}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest.write_text(
        json.dumps({"schema_version": "1.0", "entries": entries}), encoding="utf-8"
    )
    return path


def _query() -> ExperienceQuery:
    return ExperienceQuery(
        supplier="示例供应方",
        material="原竹丝",
        season="spring",
        metric="total_average",
        as_of=NOW,
    )


def test_only_approved_structured_experience_can_affect_review(tmp_path: Path) -> None:
    _write_entry(tmp_path, filename="approved.md")
    _write_entry(
        tmp_path,
        filename="pending.md",
        experience_id="EXP-PENDING",
        status="pending_review",
    )
    (tmp_path / "approved" / "notes.md").write_text(
        "普通 Markdown 仅供报告引用。", encoding="utf-8"
    )

    results = LocalApprovedExperienceRepository(tmp_path, as_of=NOW).search(_query())

    assert [item.experience_id for item in results] == ["EXP-001"]
    assert results[0].can_affect_review is True
    assert results[0].quoted_reference.startswith("> ")


def test_repository_is_read_only() -> None:
    public_names = {
        name
        for name, _ in inspect.getmembers(ExperienceRepository)
        if not name.startswith("_")
    }
    assert public_names == {"get", "search"}
    assert not public_names & {"write", "save", "update", "delete"}


def test_scope_results_are_deterministic(tmp_path: Path) -> None:
    _write_entry(tmp_path, filename="z.md", experience_id="EXP-Z")
    _write_entry(tmp_path, filename="b.md", experience_id="EXP-B")
    _write_entry(tmp_path, filename="a.md", experience_id="EXP-A")
    _write_entry(
        tmp_path,
        filename="wild.md",
        experience_id="EXP-W",
        applicable_suppliers=["*"],
        applicable_materials=["*"],
        applicable_seasons=["*"],
        applicable_metrics=["*"],
    )
    repository = LocalApprovedExperienceRepository(tmp_path, as_of=NOW)

    first = repository.search(_query())
    second = repository.search(_query())

    assert [item.experience_id for item in first] == ["EXP-A", "EXP-B", "EXP-Z", "EXP-W"]
    assert first == second


@pytest.mark.parametrize(
    "updates",
    [
        {"version": "1.0"},
        {"source": ""},
        {"evidence_sources": []},
        {"applicable_metrics": []},
        {"author": "same", "reviewer": "same"},
        {"effective_at": "2026-01-01T00:00:00"},
    ],
)
def test_invalid_schema_or_governance_is_rejected(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    _write_entry(tmp_path, **updates)
    with pytest.raises(ExperienceValidationError):
        LocalApprovedExperienceRepository(tmp_path, as_of=NOW).search(_query())


def test_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "path": "../outside.md",
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExperienceSecurityError):
        LocalApprovedExperienceRepository(tmp_path, as_of=NOW).search(_query())


def test_symlink_entry_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    approved = tmp_path / "approved"
    approved.mkdir()
    link = approved / "escape.md"
    try:
        link.symlink_to(outside)
    except OSError:
        link.write_text("simulated link", encoding="utf-8")
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == link or original_is_symlink(path),
        )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "path": "approved/escape.md",
                        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExperienceSecurityError):
        LocalApprovedExperienceRepository(tmp_path, as_of=NOW).search(_query())


def test_manifest_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    _write_entry(tmp_path)
    path = tmp_path / "approved" / "entry.md"
    path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    with pytest.raises(ExperienceValidationError, match="SHA-256"):
        LocalApprovedExperienceRepository(tmp_path, as_of=NOW).search(_query())


def test_conflicting_approved_versions_are_rejected(tmp_path: Path) -> None:
    _write_entry(tmp_path, filename="v1.md", version="1.0.0")
    _write_entry(
        tmp_path,
        filename="v2.md",
        version="2.0.0",
        supersedes="1.0.0",
    )
    with pytest.raises(ExperienceConflictError):
        LocalApprovedExperienceRepository(tmp_path, as_of=NOW).search(_query())

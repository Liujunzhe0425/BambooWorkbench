"""Experience managed-root resolver, initializer, and three-pane projections.

All paths resolve under the authorized data root; absolute paths are never
returned to callers.  The managed root is the single authoritative location
once initialised — the bundled baseline is never used as a silent fallback.
"""

from __future__ import annotations

import os
import shutil
from contextlib import suppress
from pathlib import Path

from moisture.adapters.experience.local_approved_repository import (
    LocalApprovedExperienceRepository,
)
from moisture.runtime_paths import module_root

_STATES = ("draft", "approved", "retired")

_SEED_ID = "EXP-GENERIC-001"
_SEED_VERSION = "1.0.0"


def resolve_managed_root() -> Path | None:
    """Return ``<BAMBOO_MOISTURE_DATA_DIR>/experience`` if the env var is set."""
    data_dir = os.environ.get("BAMBOO_MOISTURE_DATA_DIR")
    if not data_dir:
        return None
    return Path(data_dir).resolve() / "experience"


def resolve_bundled_root() -> Path:
    """Return the read-only baseline inside the module."""
    return (module_root() / "experience").resolve()


def resolve_runtime_experience_root() -> Path:
    """Resolve the authoritative read-only runtime projection.

    Source-tree runs without a framework data directory use the bundled
    baseline.  Once the framework supplies ``BAMBOO_MOISTURE_DATA_DIR``, the
    managed root is authoritative and is initialized exactly once.
    """

    managed_root = resolve_managed_root()
    if managed_root is None:
        return resolve_bundled_root()
    if needs_initialization(managed_root):
        initialize_managed_root(managed_root)
    return managed_root


def needs_initialization(managed_root: Path) -> bool:
    """True when the managed root is absent or completely empty."""
    if not managed_root.exists():
        return True
    if not (managed_root / "manifest.json").is_file():
        # Root exists without manifest → only init if it is truly empty
        return not any(True for _ in managed_root.iterdir())
    return False


def initialize_managed_root(managed_root: Path) -> None:
    """Copy the bundled seed into *managed_root* when it is absent or empty.

    Raises ``FileExistsError`` if a manifest already exists.
    Raises ``ValueError`` if the bundled seed cannot be validated.
    """
    if not needs_initialization(managed_root):
        raise FileExistsError(
            f"Experience managed root already initialised: {managed_root}"
        )

    bundled_root = resolve_bundled_root()
    bundled_manifest = bundled_root / "manifest.json"
    if not bundled_manifest.is_file():
        raise ValueError(
            f"Bundled experience manifest is missing: {bundled_manifest}"
        )

    import json as _json

    # Validate the complete bundled projection before creating managed files.
    # This checks the manifest, Schema, paths and every referenced SHA-256.
    LocalApprovedExperienceRepository(bundled_root).list_approved()
    manifest_data = _json.loads(bundled_manifest.read_text(encoding="utf-8"))
    entries = manifest_data.get("entries", [])
    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        if not managed_root.exists():
            managed_root.mkdir(parents=True)
            created_directories.append(managed_root)
        for state in _STATES:
            directory = managed_root / state
            if not directory.exists():
                directory.mkdir()
                created_directories.append(directory)

        for entry in entries:
            src_path = bundled_root / entry["path"]
            dst_path = managed_root / entry["path"]
            if not src_path.is_file():
                raise ValueError(f"Bundled seed file missing: {src_path}")
            shutil.copy2(src_path, dst_path)
            created_files.append(dst_path)

        # Publish the authoritative manifest last.
        tmp = managed_root / ".manifest.tmp"
        created_files.append(tmp)
        with tmp.open("x+b") as destination:
            destination.write(
                _json.dumps(
                    manifest_data,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
            )
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(tmp, managed_root / "manifest.json")
        created_files.remove(tmp)
    except BaseException:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            with suppress(OSError):
                directory.rmdir()
        raise

"""Unit tests for experience data-root resolver and initializer (E-S1)."""

from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.data_root import (
    initialize_managed_root,
    needs_initialization,
    resolve_bundled_root,
    resolve_managed_root,
)


class TestResolveManagedRoot:
    def test_returns_none_when_env_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BAMBOO_MOISTURE_DATA_DIR", raising=False)
        assert resolve_managed_root() is None

    def test_returns_experience_subdir_when_env_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("BAMBOO_MOISTURE_DATA_DIR", str(tmp_path))
        result = resolve_managed_root()
        assert result == tmp_path / "experience"

    def test_resolve_bundled_root_returns_module_experience_dir(self) -> None:
        bundled = resolve_bundled_root()
        assert bundled.is_dir()
        assert (bundled / "manifest.json").is_file()


class TestNeedsInitialization:
    def test_nonexistent_root_needs_init(self, tmp_path: Path) -> None:
        assert needs_initialization(tmp_path / "nonexistent")

    def test_existing_empty_root_needs_init(self, tmp_path: Path) -> None:
        root = tmp_path / "empty"
        root.mkdir()
        assert needs_initialization(root)

    def test_root_with_manifest_does_not_need_init(self, tmp_path: Path) -> None:
        root = tmp_path / "initialised"
        root.mkdir()
        (root / "manifest.json").write_text("{}", encoding="utf-8")
        assert not needs_initialization(root)


class TestInitializeManagedRoot:
    def test_creates_lifecycle_directories(self, tmp_path: Path) -> None:
        root = tmp_path / "exp"
        initialize_managed_root(root)
        assert (root / "draft").is_dir()
        assert (root / "approved").is_dir()
        assert (root / "retired").is_dir()

    def test_writes_manifest(self, tmp_path: Path) -> None:
        root = tmp_path / "exp"
        initialize_managed_root(root)
        assert (root / "manifest.json").is_file()

    def test_copies_approved_seed_files(self, tmp_path: Path) -> None:
        root = tmp_path / "exp"
        initialize_managed_root(root)
        approved_files = list((root / "approved").glob("*.md"))
        assert len(approved_files) >= 1

    def test_idempotent_raises(self, tmp_path: Path) -> None:
        root = tmp_path / "exp"
        initialize_managed_root(root)
        with pytest.raises(FileExistsError, match="already initialised"):
            initialize_managed_root(root)

    def test_root_without_manifest_and_with_files_is_not_initializable(
        self, tmp_path: Path
    ) -> None:
        """Root with unknown files but no manifest is a corrupt state —
        not safe for automatic initialization."""
        root = tmp_path / "exp"
        root.mkdir()
        (root / "some_file").write_text("x")
        assert not needs_initialization(root)

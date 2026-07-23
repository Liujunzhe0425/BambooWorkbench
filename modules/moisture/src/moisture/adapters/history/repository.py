"""History data repository — import, list, get, and retire analysis summary XLSX files.

Persists a ``history-index.json`` index conforming to
``history-index.schema.json`` and stores imported workbooks as
``{history_id}.xlsx`` inside the configured storage directory.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from moisture.infrastructure.atomic_write import _write_json_atomic
from moisture.infrastructure.hashing import sha256_file
from moisture.runtime_paths import module_root
from openpyxl import load_workbook

_REQUIRED_SHEETS = frozenset({"竹丝含水率统计", "异常分析明细", "趋势分析", "来源追溯"})
_FIVE_SHEET_EXTRA = "模型分析记录"
_CORE_COLUMNS = ("日期", "供应商", "均值")
_INDEX_FILENAME = "history-index.json"


# ---------------------------------------------------------------------------
#  Errors
# ---------------------------------------------------------------------------


class HistoryRepositoryError(RuntimeError):
    """Base error for history repository operations."""


class HistoryImportError(HistoryRepositoryError):
    """The source workbook cannot be imported."""


class HistoryIntegrityError(HistoryRepositoryError):
    """Index or stored file integrity violation."""


class HistorySecurityError(HistoryRepositoryError):
    """Path escapes the storage directory or contains forbidden links."""


# ---------------------------------------------------------------------------
#  Path safety helpers
# ---------------------------------------------------------------------------


def _is_reparse_point(path: Path) -> bool:
    """True when *path* is a symlink or Windows junction/reparse point."""
    linked = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(linked, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _validate_storage_dir(storage_dir: Path) -> Path:
    """Resolve *storage_dir* and reject symlinks / junctions."""
    if storage_dir.exists() and _is_reparse_point(storage_dir):
        raise HistorySecurityError("storage_dir must not be a symlink or reparse point")
    try:
        resolved = storage_dir.resolve(strict=False)
    except OSError as exc:
        raise HistorySecurityError("cannot resolve storage_dir") from exc
    # Check each ancestor against the resolved root to catch junction parents
    return resolved


def _require_regular_file(path: Path) -> Path:
    """Verify *path* is an existing regular file, not a symlink/junction."""
    try:
        if _is_reparse_point(path):
            raise HistorySecurityError("source file must not be a symlink or reparse point")
        resolved = path.resolve(strict=True)
        if _is_reparse_point(resolved):
            raise HistorySecurityError(
                "resolved source file must not be a symlink or reparse point"
            )
        linked = resolved.stat(follow_symlinks=False)
        if not stat.S_ISREG(linked.st_mode):
            raise HistorySecurityError("source must be a regular file")
    except HistorySecurityError:
        raise
    except OSError as exc:
        raise HistorySecurityError("cannot access source file") from exc
    return resolved


def _require_inside(parent: Path, child: Path) -> None:
    """Raise if *child* does not reside inside *parent*."""
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=True))
    except (ValueError, OSError) as exc:
        raise HistorySecurityError("path escapes storage directory") from exc


# ---------------------------------------------------------------------------
#  Schema & index persistence
# ---------------------------------------------------------------------------


def _index_path(storage_dir: Path) -> Path:
    return storage_dir / _INDEX_FILENAME


def _load_index_schema() -> Draft202012Validator:
    schema_path = module_root() / "schemas" / "history-index.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise HistoryIntegrityError("bundled history-index schema is invalid") from exc
    return Draft202012Validator(schema)


def _load_index(storage_dir: Path) -> dict[str, Any]:
    """Load the index file, or return a fresh empty index."""
    path = _index_path(storage_dir)
    if not path.exists():
        return {"schema_version": "1.0", "entries": []}
    _require_regular_file(path)
    _require_inside(storage_dir, path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HistoryIntegrityError("cannot parse history-index.json") from exc
    if not isinstance(payload, dict):
        raise HistoryIntegrityError("history-index.json must be a JSON object")
    validator = _load_index_schema()
    try:
        validator.validate(payload)
    except JsonSchemaValidationError as exc:
        raise HistoryIntegrityError("history-index.json does not match schema") from exc
    return payload


def _save_index(storage_dir: Path, payload: dict[str, Any]) -> None:
    """Atomically write the index file, validating against schema first."""
    validator = _load_index_schema()
    try:
        validator.validate(payload)
    except JsonSchemaValidationError as exc:
        raise HistoryIntegrityError("refusing to persist index that does not match schema") from exc
    destination = _index_path(storage_dir)
    _write_json_atomic(destination, payload)


# ---------------------------------------------------------------------------
#  Source workbook validation
# ---------------------------------------------------------------------------


def _validate_workbook_sheets(sheet_names: list[str]) -> str:
    """Accept the current four-sheet and legacy five-sheet summaries."""

    names = set(sheet_names)
    if names == _REQUIRED_SHEETS and len(sheet_names) == len(_REQUIRED_SHEETS):
        return "1.0.1-four-sheet"
    legacy_names = _REQUIRED_SHEETS | {_FIVE_SHEET_EXTRA}
    if names == legacy_names and len(sheet_names) == len(legacy_names):
        return "1.0.0-five-sheet"
    missing = _REQUIRED_SHEETS - names
    extra = names - legacy_names
    parts: list[str] = []
    if missing:
        parts.append(f"missing: {', '.join(sorted(missing))}")
    if extra:
        parts.append(f"unexpected: {', '.join(sorted(extra))}")
    if not parts:
        parts.append("duplicate or unsupported sheet layout")
    raise HistoryImportError(
        "workbook must contain the four deterministic sheets with at most "
        f"the legacy {_FIVE_SHEET_EXTRA} sheet; " + "; ".join(parts)
    )


def _validate_core_columns(sheet) -> None:
    """Check the 竹丝含水率统计 sheet contains the core column keywords.

    Scans the first 10 rows and 50 columns for header cells that contain
    the expected keywords (日期, 供应商, 均值).
    """
    found: set[str] = set()
    for row in sheet.iter_rows(min_row=1, max_row=10, max_col=50):
        for cell in row:
            if cell.value is None:
                continue
            text = str(cell.value).strip()
            for keyword in _CORE_COLUMNS:
                if keyword in text:
                    found.add(keyword)
    missing = set(_CORE_COLUMNS) - found
    if missing:
        raise HistoryImportError(
            "missing core columns in 竹丝含水率统计 sheet: " + ", ".join(sorted(missing))
        )


def _infer_batch_count(sheet) -> int:
    """Count rows with numeric data after the header region in the stats sheet."""
    count = 0
    for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row or 1000, max_col=5):
        values = [cell.value for cell in row if cell.value is not None]
        numeric = sum(1 for v in values if isinstance(v, (int, float)))
        if numeric >= 2:
            count += 1
    return count


# ---------------------------------------------------------------------------
#  Repository
# ---------------------------------------------------------------------------


class HistoryRepository:
    """Manage imported analysis summary workbooks and their index."""

    def __init__(self, storage_dir: Path) -> None:
        resolved = _validate_storage_dir(storage_dir)
        resolved.mkdir(parents=True, exist_ok=True)
        self._storage_dir = resolved

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def import_summary(self, source_xlsx_path: Path, display_name: str) -> str:
        """Import a current four-sheet or legacy five-sheet summary workbook.

        Returns the ``history_id``.  Duplicate files (same SHA-256) return
        the existing id without re-importing.
        """
        # -- validate source --
        source = _require_regular_file(source_xlsx_path)
        if source.suffix.lower() != ".xlsx":
            raise HistoryImportError("source must be an .xlsx file")

        if not isinstance(display_name, str) or not (1 <= len(display_name) <= 200):
            raise HistoryImportError("display_name must be 1-200 characters")

        # -- open workbook read-only --
        try:
            wb = load_workbook(source, read_only=True, data_only=True)
        except Exception as exc:
            raise HistoryImportError("cannot open source as a valid XLSX workbook") from exc

        try:
            sheet_names = wb.sheetnames
            format_version = _validate_workbook_sheets(sheet_names)

            stats_sheet = wb["竹丝含水率统计"]
            _validate_core_columns(stats_sheet)
            batch_count = _infer_batch_count(stats_sheet)
        finally:
            wb.close()

        # -- deduplicate by content hash --
        file_hash = sha256_file(source)
        index = _load_index(self._storage_dir)
        for entry in index["entries"]:
            if entry["sha256"] == file_hash:
                return entry["history_id"]

        # -- generate id and copy file --
        history_id = uuid.uuid4().hex
        storage_name = f"{history_id}.xlsx"
        dest = self._storage_dir / storage_name

        self._copy_atomic(source, dest)

        # -- persist index entry --
        entry: dict[str, Any] = {
            "history_id": history_id,
            "display_name": display_name,
            "storage_name": storage_name,
            "sha256": file_hash,
            "format_version": format_version,
            "date_start": None,
            "date_end": None,
            "batch_count": batch_count,
            "status": "active",
        }
        index["entries"].append(entry)
        _verify_all_stored_hashes(self._storage_dir, index)
        _save_index(self._storage_dir, index)

        return history_id

    def list_entries(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        """Return all index entries, optionally filtered by *status_filter*."""
        index = _load_index(self._storage_dir)
        entries = index["entries"]
        if status_filter is not None:
            entries = [e for e in entries if e.get("status") == status_filter]
        return list(entries)

    def get_entry(self, history_id: str) -> dict[str, Any] | None:
        """Return the entry for *history_id*, or ``None``."""
        index = _load_index(self._storage_dir)
        for entry in index["entries"]:
            if entry["history_id"] == history_id:
                return dict(entry)
        return None

    def resolve_active_summary(self, history_id: str) -> Path:
        """Return a verified stored workbook path for one active stable ID."""

        entry = self.get_entry(history_id)
        if entry is None:
            raise HistoryIntegrityError("selected history entry does not exist")
        if entry["status"] != "active":
            raise HistoryIntegrityError("selected history entry is not active")
        path = self._storage_dir / entry["storage_name"]
        _require_regular_file(path)
        _require_inside(self._storage_dir, path)
        if sha256_file(path) != entry["sha256"]:
            raise HistoryIntegrityError("selected history file hash does not match index")
        return path

    def retire_entry(self, history_id: str) -> None:
        """Set the status of *history_id* to ``retired`` (idempotent).

        Raises ``KeyError`` if the entry does not exist.
        """
        index = _load_index(self._storage_dir)
        for entry in index["entries"]:
            if entry["history_id"] == history_id:
                if entry["status"] == "retired":
                    return
                entry["status"] = "retired"
                _verify_all_stored_hashes(self._storage_dir, index)
                _save_index(self._storage_dir, index)
                return
        raise KeyError(f"history entry not found: {history_id}")

    # ------------------------------------------------------------------
    #  Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _copy_atomic(source: Path, dest: Path) -> None:
        """Copy *source* to *dest* via a temporary file + ``os.replace``."""
        tmp = dest.parent / f".{dest.name}.{uuid.uuid4().hex}.tmp"
        try:
            with open(source, "rb") as src, open(tmp, "xb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(tmp, dest)
        except Exception:
            with suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise


def _verify_all_stored_hashes(storage_dir: Path, index: dict[str, Any]) -> None:
    """Re-hash every stored workbook and verify it matches the index record.

    Called before every index save (import / retire) as an integrity
    guard per the spec: "每次 import/retire 重新计算索引中每条的 sha256".
    """
    for entry in index["entries"]:
        storage_name = entry["storage_name"]
        stored_path = storage_dir / storage_name
        _require_regular_file(stored_path)
        _require_inside(storage_dir, stored_path)
        actual = sha256_file(stored_path)
        if actual != entry["sha256"]:
            raise HistoryIntegrityError(
                f"stored file hash mismatch for {storage_name}: "
                f"index={entry['sha256'][:12]}... actual={actual[:12]}..."
            )

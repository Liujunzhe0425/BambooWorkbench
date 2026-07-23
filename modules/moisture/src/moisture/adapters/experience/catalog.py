"""Approved experience catalog — read-only snapshot for AI report consumption."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import yaml
from moisture.adapters.experience.local_approved_repository import (
    ExperienceValidationError,
    _is_reparse_point,
)
from moisture.runtime_paths import module_root

_CATALOG_SCHEMA_PATH = module_root() / "schemas" / "approved-experience-catalog.schema.json"
_MAX_ENTRIES = 1000


def build_approved_catalog(experience_root: Path, *, as_of: date | None = None) -> dict:
    """Build an approved-experience catalog dict, validated against the catalog schema.

    Parameters
    ----------
    experience_root:
        The experience repository root containing manifest.json and approved/*.md.
    as_of:
        Reference date for effective-period filtering. Defaults to today (UTC).

    Returns
    -------
    dict
        A dict with ``schema_version`` (``"1.0"``) and ``entries``, each holding
        ``entry_id``, ``title``, ``version``, ``scope``, ``effective_from``,
        ``effective_to``, and ``sha256``.

    Raises
    ------
    ExperienceValidationError
        If the catalog content fails schema validation.
    """
    root = _resolve_root(experience_root)
    manifest_entries = _read_manifest(root)
    today = as_of or date.today()

    catalog_entries: list[dict] = []
    for relative_path, expected_digest in manifest_entries:
        entry_path = root / relative_path
        raw_content = _read_regular_file(entry_path)
        actual_digest = hashlib.sha256(raw_content).hexdigest()
        if actual_digest != expected_digest:
            raise ExperienceValidationError(f"catalog entry SHA-256 mismatch: {relative_path}")

        text = raw_content.decode("utf-8")
        front_matter, _ = _parse_front_matter(text)

        status = front_matter.get("status")
        if status != "approved":
            continue

        effective_from = _extract_effective_from(front_matter)
        effective_to = _extract_effective_to(front_matter)

        if not _is_currently_effective(effective_from, effective_to, today):
            continue

        entry = _build_entry(
            front_matter=front_matter,
            sha256_digest=actual_digest,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        catalog_entries.append(entry)

    catalog = {"schema_version": "1.0", "entries": catalog_entries}

    _validate_catalog(catalog)

    return catalog


def _resolve_root(root: Path) -> Path:
    configured = Path(root)
    try:
        if _is_reparse_point(configured):
            raise ExperienceValidationError("experience root must not be a link or reparse point")
        resolved = configured.resolve(strict=True)
    except OSError as error:
        raise ExperienceValidationError("experience root does not exist") from error
    if not resolved.is_dir():
        raise ExperienceValidationError("experience root must be a directory")
    return resolved


def _read_manifest(root: Path) -> list[tuple[Path, str]]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ExperienceValidationError("manifest.json missing")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExperienceValidationError("invalid manifest.json") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "entries"}
        or payload["schema_version"] != "1.0"
        or not isinstance(payload["entries"], list)
    ):
        raise ExperienceValidationError("unsupported manifest structure")
    entries: list[tuple[Path, str]] = []
    for item in payload["entries"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ExperienceValidationError("invalid manifest entry shape")
        relative = Path(item["path"])
        digest = item["sha256"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ExperienceValidationError("manifest sha256 must be 64 hex chars")
        entries.append((relative, digest))
    return entries


def _read_regular_file(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ExperienceValidationError(f"cannot read entry: {path}") from error


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse YAML front matter from an experience Markdown document.

    Reuses the same conventions as LocalApprovedExperienceRepository.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ExperienceValidationError("experience document requires YAML front matter")
    try:
        closing = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as error:
        raise ExperienceValidationError("experience front matter is not closed") from error
    payload = yaml.safe_load("\n".join(lines[1:closing]))
    if not isinstance(payload, dict):
        raise ExperienceValidationError("experience front matter must be an object")
    body = "\n".join(lines[closing + 1 :]).strip()
    return payload, body


def _extract_effective_from(front_matter: dict) -> date:
    raw = front_matter.get("effective_at")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    raise ExperienceValidationError("effective_at must be a date-time")


def _extract_effective_to(front_matter: dict) -> date | None:
    raw = front_matter.get("effective_to")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    raise ExperienceValidationError("effective_to must be a date-time or null")


def _is_currently_effective(
    effective_from: date,
    effective_to: date | None,
    today: date,
) -> bool:
    if effective_from > today:
        return False
    return effective_to is None or effective_to >= today


def _build_entry(
    front_matter: dict,
    sha256_digest: str,
    effective_from: date,
    effective_to: date | None,
) -> dict:
    suppliers = _format_list(front_matter.get("applicable_suppliers", []))
    materials = _format_list(front_matter.get("applicable_materials", []))
    seasons = _format_list(front_matter.get("applicable_seasons", []))
    metrics = _format_list(front_matter.get("applicable_metrics", []))
    scope = (
        f"suppliers: {suppliers}; materials: {materials}; seasons: {seasons}; metrics: {metrics}"
    )

    return {
        "entry_id": front_matter["experience_id"],
        "title": front_matter["title"],
        "version": front_matter["version"],
        "scope": scope[:500],
        "effective_from": effective_from.isoformat(),
        "effective_to": effective_to.isoformat() if effective_to is not None else None,
        "sha256": sha256_digest,
    }


def _format_list(values: list) -> str:
    if not values:
        return "any"
    return ",".join(str(v) for v in values)


def _validate_catalog(catalog: dict) -> None:
    from jsonschema import Draft202012Validator

    schema_text = _CATALOG_SCHEMA_PATH.read_text(encoding="utf-8")
    schema = json.loads(schema_text)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(catalog))
    if errors:
        messages = "; ".join(
            f"{' '.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors
        )
        raise ExperienceValidationError(f"catalog schema validation failed: {messages}")

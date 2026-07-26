"""Safe output-directory manifests used for history recovery."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from core.contracts.result import OutputArtifact

MANIFEST_NAME = ".bamboo-task.json"
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class OutputManifestMetadata:
    installation_id: str
    job_id: str
    task_name: str
    module_id: str
    year: int
    month: int
    created_at: str
    completed_at: str
    committed_at: str
    snapshot_format: str
    snapshot_sha256: str
    replacement_for_job_id: str | None = None
    transaction_id: str | None = None


def write_output_manifest(
    directory: Path,
    metadata: OutputManifestMetadata,
    outputs: list[OutputArtifact],
) -> Path:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("output manifest directory is not trusted")
    artifact_records: list[dict[str, object]] = []
    for artifact in outputs:
        path = Path(artifact.path).resolve(strict=True)
        if not path.is_relative_to(directory.resolve()) or path.is_symlink() or not path.is_file():
            raise ValueError("output manifest artifact is outside the result directory")
        relative = path.relative_to(directory.resolve()).as_posix()
        artifact_records.append(
            {
                "path": relative,
                "type": artifact.type,
                "label": artifact.label,
                "mime_type": artifact.mime_type,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    payload: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "installation_id": metadata.installation_id,
        "job_id": metadata.job_id,
        "task_name": metadata.task_name,
        "module_id": metadata.module_id,
        "year": metadata.year,
        "month": metadata.month,
        "created_at": metadata.created_at,
        "completed_at": metadata.completed_at,
        "committed_at": metadata.committed_at,
        "snapshot": {
            "format": metadata.snapshot_format,
            "sha256": metadata.snapshot_sha256,
        },
        "replacement_for_job_id": metadata.replacement_for_job_id,
        "transaction_id": metadata.transaction_id,
        "outputs": artifact_records,
        "official": True,
        "superseded_by_transaction_id": None,
    }
    payload["manifest_sha256"] = _payload_digest(payload)
    path = directory / MANIFEST_NAME
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _mark_hidden_read_only(path)
    return path


def validate_output_manifest(path: Path) -> dict[str, object]:
    if path.name != MANIFEST_NAME or not path.is_file() or path.is_symlink():
        raise ValueError("result manifest is not a trusted file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("result manifest is invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("result manifest schema is unsupported")
    if not isinstance(payload.get("official"), bool):
        raise ValueError("result manifest official state is invalid")
    supplied_digest = payload.get("manifest_sha256")
    digest_payload = dict(payload)
    digest_payload.pop("manifest_sha256", None)
    if supplied_digest != _payload_digest(digest_payload):
        raise ValueError("result manifest digest mismatch")
    required_strings = (
        "installation_id",
        "job_id",
        "task_name",
        "module_id",
        "created_at",
        "completed_at",
        "committed_at",
    )
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in required_strings):
        raise ValueError("result manifest identity is incomplete")
    year, month = payload.get("year"), payload.get("month")
    if not isinstance(year, int) or not 2000 <= year <= 9999:
        raise ValueError("result manifest year is invalid")
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("result manifest month is invalid")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("result manifest outputs are invalid")
    root = path.parent.resolve()
    for record in outputs:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError("result manifest artifact record is invalid")
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("result manifest artifact path escapes the result directory")
        artifact = (root / relative).resolve(strict=True)
        if not artifact.is_relative_to(root) or not artifact.is_file() or artifact.is_symlink():
            raise ValueError("result manifest artifact is unavailable")
        if artifact.stat().st_size != record.get("size") or _sha256(artifact) != record.get(
            "sha256"
        ):
            raise ValueError("result manifest artifact integrity check failed")
    return payload


def mark_output_manifest_superseded(path: Path, transaction_id: str) -> None:
    payload = validate_output_manifest(path)
    if not payload["official"]:
        return
    path.chmod(0o666)
    payload["official"] = False
    payload["superseded_by_transaction_id"] = transaction_id
    payload.pop("manifest_sha256", None)
    payload["manifest_sha256"] = _payload_digest(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _mark_hidden_read_only(path)


def scan_output_manifests(roots: tuple[Path, ...]) -> list[tuple[Path, dict[str, object]]]:
    found: list[tuple[Path, dict[str, object]]] = []
    visited: set[Path] = set()
    for raw_root in roots:
        try:
            root = raw_root.resolve(strict=True)
        except OSError:
            continue
        if root in visited or not root.is_dir() or root.is_symlink():
            continue
        visited.add(root)
        try:
            children = tuple(root.iterdir())
        except OSError:
            continue
        for child in children:
            manifest = child / MANIFEST_NAME
            if not child.is_dir() or child.is_symlink() or not manifest.is_file():
                continue
            try:
                found.append((manifest, validate_output_manifest(manifest)))
            except (OSError, ValueError):
                continue
    return found


def _payload_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mark_hidden_read_only(path: Path) -> None:
    try:
        path.chmod(0o444)
        if os.name == "nt":
            import ctypes

            attributes = 0x1 | 0x2  # FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes)
    except OSError:
        # Integrity is provided by the digest. Attributes are a user-facing
        # guardrail and may be unavailable on non-NT test filesystems.
        return

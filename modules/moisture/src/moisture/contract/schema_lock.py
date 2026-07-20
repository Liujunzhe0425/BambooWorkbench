"""Runtime verification for the module-local framework schema bundle."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from moisture.runtime_paths import module_root as runtime_module_root

SCHEMA_NAMES = (
    "job-request.schema.json",
    "module-manifest.schema.json",
    "module-result.schema.json",
)
LOCK_RELATIVE_PATH = "schemas/contracts/schema-lock.json"
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SchemaBundleError(RuntimeError):
    """A stable failure to read or verify a bundled schema."""


def _default_module_root() -> Path:
    return runtime_module_root()


def _expected_paths() -> tuple[str, ...]:
    return tuple(f"schemas/contracts/{name}" for name in SCHEMA_NAMES)


def collect_schema_lock_issues(module_root: Path | None = None) -> tuple[str, ...]:
    root = module_root or _default_module_root()
    lock_path = root / LOCK_RELATIVE_PATH
    try:
        raw_lock = lock_path.read_text(encoding="utf-8")
        lock = json.loads(raw_lock)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ("schema lock is missing or invalid JSON",)

    issues: list[str] = []
    if not isinstance(lock, dict) or set(lock) != {"schema_version", "schemas"}:
        return ("schema lock has an invalid structure",)
    if lock["schema_version"] != 1 or not isinstance(lock["schemas"], dict):
        return ("schema lock has an unsupported version or schema map",)

    schemas = lock["schemas"]
    expected_paths = set(_expected_paths())
    if set(schemas) != expected_paths:
        issues.append("schema lock does not list the required schema set")

    deterministic = json.dumps(
        lock, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if raw_lock != deterministic:
        issues.append("schema lock is not in deterministic form")

    for relative_path in sorted(expected_paths):
        pure_path = PurePosixPath(relative_path)
        expected_hash = schemas.get(relative_path)
        if (
            pure_path.is_absolute()
            or ".." in pure_path.parts
            or "\\" in relative_path
            or not isinstance(expected_hash, str)
            or not _HASH_PATTERN.fullmatch(expected_hash)
        ):
            issues.append(f"schema lock entry is invalid: {pure_path.name}")
            continue

        schema_path = root.joinpath(*pure_path.parts)
        try:
            content = schema_path.read_bytes()
        except OSError:
            issues.append(f"bundled schema is missing: {pure_path.name}")
            continue
        if hashlib.sha256(content).hexdigest() != expected_hash:
            issues.append(f"bundled schema hash mismatch: {pure_path.name}")
            continue
        try:
            parsed = json.loads(content)
        except (UnicodeError, json.JSONDecodeError):
            issues.append(f"bundled schema is invalid JSON: {pure_path.name}")
        else:
            if not isinstance(parsed, dict):
                issues.append(f"bundled schema is not an object: {pure_path.name}")

    return tuple(issues)


def require_valid_schema_bundle(module_root: Path | None = None) -> None:
    issues = collect_schema_lock_issues(module_root)
    if issues:
        raise SchemaBundleError(issues[0])


def load_bundled_schema(
    name: str, module_root: Path | None = None
) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise SchemaBundleError("unknown bundled schema requested")
    root = module_root or _default_module_root()
    require_valid_schema_bundle(root)
    try:
        payload = json.loads((root / "schemas" / "contracts" / name).read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SchemaBundleError("bundled schema cannot be loaded") from error
    if not isinstance(payload, dict):
        raise SchemaBundleError("bundled schema is not an object")
    return payload

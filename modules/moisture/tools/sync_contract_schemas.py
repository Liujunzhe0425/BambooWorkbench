"""Synchronize the module's development-time copies of framework schemas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

SCHEMA_NAMES = (
    "job-request.schema.json",
    "module-manifest.schema.json",
    "module-result.schema.json",
)


def _paths() -> tuple[Path, Path]:
    module_root = Path(__file__).resolve().parents[1]
    repository_root = Path(__file__).resolve().parents[3]
    canonical_dir = repository_root / "contracts" / "schemas"
    if not canonical_dir.is_dir() or module_root.parent.name != "modules":
        raise RuntimeError("unable to locate canonical framework schemas")
    return module_root, canonical_dir


def _lock_bytes(module_root: Path, canonical_dir: Path) -> bytes:
    schemas = {
        f"schemas/contracts/{name}": hashlib.sha256(
            (canonical_dir / name).read_bytes()
        ).hexdigest()
        for name in SCHEMA_NAMES
    }
    payload = {"schema_version": 1, "schemas": schemas}
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def check() -> tuple[str, ...]:
    module_root, canonical_dir = _paths()
    bundled_dir = module_root / "schemas" / "contracts"
    issues: list[str] = []
    for name in SCHEMA_NAMES:
        canonical = canonical_dir / name
        bundled = bundled_dir / name
        if not canonical.is_file():
            issues.append(f"canonical schema is missing: {name}")
        elif not bundled.is_file():
            issues.append(f"bundled schema is missing: {name}")
        elif bundled.read_bytes() != canonical.read_bytes():
            issues.append(f"bundled schema differs from canonical: {name}")

    lock_path = bundled_dir / "schema-lock.json"
    if not lock_path.is_file():
        issues.append("schema lock is missing")
    elif lock_path.read_bytes() != _lock_bytes(module_root, canonical_dir):
        issues.append("schema lock differs from canonical hashes")
    return tuple(issues)


def sync() -> None:
    module_root, canonical_dir = _paths()
    bundled_dir = module_root / "schemas" / "contracts"
    for name in SCHEMA_NAMES:
        source = canonical_dir / name
        if not source.is_file():
            raise RuntimeError(f"canonical schema is missing: {name}")
        _atomic_write(bundled_dir / name, source.read_bytes())
    _atomic_write(
        bundled_dir / "schema-lock.json", _lock_bytes(module_root, canonical_dir)
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--sync", action="store_true")
    parsed = parser.parse_args(arguments)

    try:
        if parsed.sync:
            sync()
            return 0
        issues = check()
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as error:
        sys.stderr.write(f"schema sync: {error}\n")
        return 1

    for issue in issues:
        sys.stderr.write(f"schema sync: {issue}\n")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

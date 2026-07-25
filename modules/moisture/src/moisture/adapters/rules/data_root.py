"""Authoritative managed rule root and immutable runtime snapshot resolution."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from moisture.adapters.rules.package_loader import (
    RulePackageIntegrityError,
    RulePackageLoader,
    RulePackageValidationError,
)
from moisture.domain.rules import RulePackageSnapshot
from moisture.runtime_paths import module_root

_SAFE_VERSION = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ManagedRuleError(ValueError):
    """The managed rule store or requested snapshot is invalid."""


def resolve_managed_rules_root() -> Path | None:
    data_dir = os.environ.get("BAMBOO_MOISTURE_DATA_DIR")
    if not data_dir:
        return None
    return Path(data_dir).resolve() / "rules"


def resolve_bundled_rules_package() -> Path:
    return (module_root() / "rules" / "active").resolve()


def needs_rules_initialization(root: Path) -> bool:
    if not root.exists():
        return True
    if not (root / "active.json").is_file():
        return not any(root.iterdir())
    return False


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as destination:
            json.dump(payload, destination, ensure_ascii=False, indent=2, sort_keys=True)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_managed_rules_root(root: Path) -> None:
    """Seed the managed store from the validated bundled active package."""

    if not needs_rules_initialization(root):
        raise FileExistsError("managed rules root is already initialized")
    bundled = resolve_bundled_rules_package()
    snapshot = RulePackageLoader().load(bundled)
    created: list[Path] = []
    try:
        root.mkdir(parents=True, exist_ok=True)
        for name in ("drafts", "versions"):
            directory = root / name
            directory.mkdir(exist_ok=True)
        target = root / "versions" / snapshot.rule_version
        shutil.copytree(bundled, target)
        created.append(target)
        _atomic_json(
            root / "retired.json",
            {"schema_version": "1.0", "entries": []},
        )
        created.append(root / "retired.json")
        _atomic_json(
            root / "active.json",
            {
                "schema_version": "1.0",
                "active": {
                    "rule_version": snapshot.rule_version,
                    "rules_sha256": snapshot.rules_sha256,
                },
            },
        )
    except BaseException:
        for path in reversed(created):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        raise


def _read_pointer(root: Path) -> dict[str, str] | None:
    path = root / "active.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManagedRuleError("active rule pointer is invalid") from error
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "active"}:
        raise ManagedRuleError("active rule pointer has an invalid structure")
    if payload["schema_version"] != "1.0":
        raise ManagedRuleError("active rule pointer version is unsupported")
    active = payload["active"]
    if active is None:
        return None
    if (
        not isinstance(active, dict)
        or set(active) != {"rule_version", "rules_sha256"}
        or not isinstance(active["rule_version"], str)
        or _SAFE_VERSION.fullmatch(active["rule_version"]) is None
        or not isinstance(active["rules_sha256"], str)
        or __import__("re").fullmatch(r"[0-9a-f]{64}", active["rules_sha256"]) is None
    ):
        raise ManagedRuleError("active rule identity is invalid")
    return active


def _retired_identities(root: Path) -> set[tuple[str, str]]:
    path = root / "retired.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManagedRuleError("retired rule index is invalid") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "entries"}
        or payload["schema_version"] != "1.0"
        or not isinstance(payload["entries"], list)
    ):
        raise ManagedRuleError("retired rule index has an invalid structure")
    result: set[tuple[str, str]] = set()
    for item in payload["entries"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"rule_version", "rules_sha256"}
            or not isinstance(item["rule_version"], str)
            or _SAFE_VERSION.fullmatch(item["rule_version"]) is None
            or not isinstance(item["rules_sha256"], str)
            or __import__("re").fullmatch(r"[0-9a-f]{64}", item["rules_sha256"]) is None
        ):
            raise ManagedRuleError("retired rule identity is invalid")
        identity = (item["rule_version"], item["rules_sha256"])
        if identity in result:
            raise ManagedRuleError("retired rule identity is duplicated")
        result.add(identity)
    return result


def load_runtime_rule_snapshot(
    *,
    rule_version: str | None = None,
    rules_sha256: str | None = None,
    bundled_package: Path | None = None,
) -> RulePackageSnapshot:
    """Load the active or explicitly pinned immutable package without fallback."""

    if (rule_version is None) is not (rules_sha256 is None):
        raise ManagedRuleError("rule version and SHA-256 must be supplied together")
    managed = resolve_managed_rules_root()
    if managed is None:
        package = bundled_package or resolve_bundled_rules_package()
        snapshot = RulePackageLoader().load(package)
    else:
        if needs_rules_initialization(managed):
            initialize_managed_rules_root(managed)
        if rule_version is None:
            active = _read_pointer(managed)
            if active is None:
                raise ManagedRuleError("no active rule package is configured")
            selected_version = active["rule_version"]
            selected_hash = active["rules_sha256"]
        else:
            selected_version = rule_version
            selected_hash = rules_sha256
        if (selected_version, selected_hash) in _retired_identities(managed):
            raise ManagedRuleError("selected rule package is retired")
        package = managed / "versions" / selected_version
        try:
            resolved_versions = (managed / "versions").resolve(strict=True)
            resolved_package = package.resolve(strict=True)
        except OSError as error:
            raise ManagedRuleError("selected rule package is missing") from error
        if resolved_package.parent != resolved_versions:
            raise ManagedRuleError("selected rule package escapes the managed store")
        snapshot = RulePackageLoader().load(resolved_package)
    if rule_version is not None and snapshot.rule_version != rule_version:
        raise ManagedRuleError("selected rule version does not match the package")
    expected_hash = rules_sha256
    if managed is not None and rule_version is None:
        expected_hash = selected_hash
    if expected_hash is not None and snapshot.rules_sha256 != expected_hash:
        raise ManagedRuleError("selected rule SHA-256 does not match the package")
    return snapshot


__all__ = [
    "ManagedRuleError",
    "_atomic_json",
    "_read_pointer",
    "_retired_identities",
    "initialize_managed_rules_root",
    "load_runtime_rule_snapshot",
    "needs_rules_initialization",
    "resolve_bundled_rules_package",
    "resolve_managed_rules_root",
    "RulePackageIntegrityError",
    "RulePackageValidationError",
]

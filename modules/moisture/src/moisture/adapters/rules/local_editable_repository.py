"""Single-user file repository for lightweight governed rule packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from moisture.adapters.history.summary_reader import StandardSummaryReader
from moisture.adapters.rules.builtin_evaluators import default_registry, evaluate_rules
from moisture.adapters.rules.data_root import (
    _atomic_json,
    _read_pointer,
    _retired_identities,
    initialize_managed_rules_root,
    needs_rules_initialization,
)
from moisture.adapters.rules.package_loader import RulePackageLoader
from moisture.domain.rules import RuleDefinition, RulePackageSnapshot

_NUMERIC_FIELDS = {
    "total_average",
    "mean",
    "minimum",
    "maximum",
    "range_value",
    "standard_deviation",
    "median",
    "first_quartile",
    "third_quartile",
    "interquartile_range",
    "maximum_department_average_difference",
    "total_weight_kg",
}
_MISSING_FIELDS = {
    "supplier",
    "material_type",
    "arrival_date",
    "test_date",
    "total_weight_kg",
    "source_file",
    "source_sheet",
}


class RuleAdminError(RuntimeError):
    pass


class RuleAdminConflictError(RuleAdminError):
    pass


class RuleAdminValidationError(RuleAdminError):
    pass


@dataclass(frozen=True, slots=True)
class RuleAdminSummary:
    rule_version: str
    package_id: str
    lifecycle: str
    rules_sha256: str
    package_hash: str
    source: str
    applicable_scope: str
    confirmation_status: str


@dataclass(frozen=True, slots=True)
class RulePreview:
    batch_count: int
    matched_batch_count: int
    decision_count: int
    pending_match_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleAdminPackage:
    summary: RuleAdminSummary
    manifest: dict[str, object]
    rules_yaml: str


def _package_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for name in ("rule-package.json", "rules.yaml"):
        content = (path / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def _supported(snapshot: RulePackageSnapshot) -> None:
    registered = default_registry().registered_types
    seen: set[str] = set()
    for definition in snapshot.definitions:
        if definition.rule_type not in registered:
            raise RuleAdminValidationError(
                f"unsupported rule type: {definition.rule_type}"
            )
        if (
            definition.rule_type in {"numeric_threshold", "numeric_range"}
            and definition.field not in _NUMERIC_FIELDS
        ):
            raise RuleAdminValidationError(
                f"unsupported numeric field: {definition.field}"
            )
        if definition.rule_type == "missing_field":
            unknown = set(definition.fields) - _MISSING_FIELDS
            if unknown:
                raise RuleAdminValidationError(
                    f"unsupported missing field: {sorted(unknown)[0]}"
                )
        if definition.rule_type == "composite" and any(
            rule_id not in seen for rule_id in definition.rule_ids
        ):
            raise RuleAdminValidationError(
                "composite rules may reference only earlier definitions"
            )
        seen.add(definition.rule_id)


def _warnings(definitions: tuple[RuleDefinition, ...]) -> tuple[str, ...]:
    warnings: set[str] = set()
    signatures: dict[tuple[object, ...], str] = {}
    targets: dict[tuple[object, ...], RuleDefinition] = {}
    for definition in definitions:
        signature = (
            definition.rule_type,
            definition.field,
            definition.operator,
            definition.threshold,
            definition.lower,
            definition.upper,
            definition.mode,
            definition.applicable_materials,
            definition.applicable_seasons,
            definition.applicable_suppliers,
        )
        previous_id = signatures.get(signature)
        if previous_id is not None:
            warnings.add(
                f"duplicate:{previous_id}:{definition.rule_id}"
            )
        signatures[signature] = definition.rule_id
        target = (
            definition.rule_type,
            definition.field,
            definition.operator,
            definition.applicable_materials,
            definition.applicable_seasons,
            definition.applicable_suppliers,
        )
        previous = targets.get(target)
        if (
            previous is not None
            and previous.threshold is not None
            and definition.threshold is not None
            and previous.threshold != definition.threshold
        ):
            warnings.add(
                f"threshold_conflict:{previous.rule_id}:{definition.rule_id}"
            )
        targets[target] = definition
    return tuple(sorted(warnings))


class LocalEditableRuleRepository:
    """Offline manager. Formal draft/finalize code must never import it."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        if needs_rules_initialization(self._root):
            initialize_managed_rules_root(self._root)
        self._root = self._root.resolve(strict=True)
        _read_pointer(self._root)
        _retired_identities(self._root)

    def _package(self, lifecycle: str, version: str) -> Path:
        allowed = (
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789._-"
        )
        if not version or any(character not in allowed for character in version):
            raise RuleAdminValidationError("unsafe rule version")
        return self._root / lifecycle / version

    def _load(self, path: Path) -> RulePackageSnapshot:
        try:
            snapshot = RulePackageLoader().load(path)
            _supported(snapshot)
            return snapshot
        except (OSError, ValueError) as error:
            if isinstance(error, RuleAdminError):
                raise
            raise RuleAdminValidationError("invalid rule package") from error

    def _summary(self, path: Path, lifecycle: str) -> RuleAdminSummary:
        snapshot = self._load(path)
        return RuleAdminSummary(
            rule_version=snapshot.rule_version,
            package_id=snapshot.package_id,
            lifecycle=lifecycle,
            rules_sha256=snapshot.rules_sha256,
            package_hash=_package_hash(path),
            source=snapshot.source,
            applicable_scope=snapshot.applicable_scope,
            confirmation_status=snapshot.customer_confirmation_status,
        )

    def list_drafts(self) -> list[RuleAdminSummary]:
        return [
            self._summary(path, "draft")
            for path in sorted((self._root / "drafts").iterdir())
            if path.is_dir()
        ]

    def list_current(self) -> list[RuleAdminSummary]:
        active = _read_pointer(self._root)
        if active is None:
            return []
        return [
            self._summary(
                self._package("versions", active["rule_version"]),
                "current",
            )
        ]

    def list_history(self) -> list[RuleAdminSummary]:
        active = _read_pointer(self._root)
        active_version = active["rule_version"] if active else None
        retired = _retired_identities(self._root)
        items: list[RuleAdminSummary] = []
        for path in sorted((self._root / "versions").iterdir()):
            if not path.is_dir() or path.name == active_version:
                continue
            summary = self._summary(path, "history")
            lifecycle = (
                "retired"
                if (summary.rule_version, summary.rules_sha256) in retired
                else "history"
            )
            items.append(
                RuleAdminSummary(
                    **{
                        field: getattr(summary, field)
                        for field in summary.__dataclass_fields__
                        if field != "lifecycle"
                    },
                    lifecycle=lifecycle,
                )
            )
        return items

    def show_package(self, version: str) -> RuleAdminPackage:
        candidates = [
            ("draft", self._package("drafts", version)),
            ("version", self._package("versions", version)),
        ]
        existing = [(kind, path) for kind, path in candidates if path.is_dir()]
        if not existing:
            raise KeyError(f"rule package not found: {version}")
        if len(existing) != 1:
            raise RuleAdminConflictError("rule version exists in multiple lifecycles")
        kind, path = existing[0]
        if kind == "draft":
            lifecycle = "draft"
        else:
            active = _read_pointer(self._root)
            retired = _retired_identities(self._root)
            summary = self._summary(path, "history")
            if active is not None and active["rule_version"] == version:
                lifecycle = "current"
            elif (summary.rule_version, summary.rules_sha256) in retired:
                lifecycle = "retired"
            else:
                lifecycle = "history"
        summary = self._summary(path, lifecycle)
        try:
            manifest = json.loads(
                (path / "rule-package.json").read_text(encoding="utf-8")
            )
            rules_yaml = (path / "rules.yaml").read_text(encoding="utf-8")
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuleAdminValidationError("invalid rule package content") from error
        if not isinstance(manifest, dict):
            raise RuleAdminValidationError("invalid rule package manifest")
        return RuleAdminPackage(summary, manifest, rules_yaml)

    def _write_package(
        self,
        target: Path,
        manifest: dict[str, object],
        rules_yaml: str,
        *,
        replace: bool,
    ) -> RuleAdminSummary:
        version = manifest.get("rule_version")
        if not isinstance(version, str) or target.name != version:
            raise RuleAdminValidationError("rule version does not match target")
        rules_bytes = rules_yaml.encode("utf-8")
        normalized = {
            **manifest,
            "rules_file": "rules.yaml",
            "rules_sha256": hashlib.sha256(rules_bytes).hexdigest(),
        }
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        backup = target.parent / f".{target.name}.{uuid.uuid4().hex}.bak"
        try:
            temporary.mkdir()
            (temporary / "rules.yaml").write_bytes(rules_bytes)
            (temporary / "rule-package.json").write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            self._load(temporary)
            if target.exists():
                if not replace:
                    raise RuleAdminConflictError("rule version already exists")
                os.replace(target, backup)
            os.replace(temporary, target)
            if backup.exists():
                shutil.rmtree(backup)
            return self._summary(target, "draft")
        except BaseException:
            if backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
            shutil.rmtree(backup, ignore_errors=True)

    def create_draft(
        self, manifest: dict[str, object], rules_yaml: str
    ) -> RuleAdminSummary:
        version = manifest.get("rule_version")
        if not isinstance(version, str):
            raise RuleAdminValidationError("rule_version is required")
        target = self._package("drafts", version)
        if target.exists() or self._package("versions", version).exists():
            raise RuleAdminConflictError("rule version already exists")
        return self._write_package(target, manifest, rules_yaml, replace=False)

    def update_draft(
        self,
        version: str,
        manifest: dict[str, object],
        rules_yaml: str,
        expected_package_hash: str,
    ) -> RuleAdminSummary:
        target = self._package("drafts", version)
        current = self._summary(target, "draft")
        if current.package_hash != expected_package_hash:
            raise RuleAdminConflictError("expected package hash does not match")
        return self._write_package(target, manifest, rules_yaml, replace=True)

    def validate_draft(self, version: str) -> RuleAdminSummary:
        return self._summary(self._package("drafts", version), "draft")

    def publish(
        self, version: str, expected_package_hash: str
    ) -> RuleAdminSummary:
        source = self._package("drafts", version)
        draft = self._summary(source, "draft")
        if draft.package_hash != expected_package_hash:
            raise RuleAdminConflictError("expected package hash does not match")
        if draft.confirmation_status != "confirmed":
            raise RuleAdminValidationError(
                "only explicitly confirmed rules can be published"
            )
        target = self._package("versions", version)
        if target.exists():
            raise RuleAdminConflictError("published rule version already exists")
        shutil.copytree(source, target)
        try:
            published = self._summary(target, "current")
            _atomic_json(
                self._root / "active.json",
                {
                    "schema_version": "1.0",
                    "active": {
                        "rule_version": published.rule_version,
                        "rules_sha256": published.rules_sha256,
                    },
                },
            )
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
        shutil.rmtree(source)
        return published

    def retire_current(self, expected_rules_sha256: str) -> RuleAdminSummary:
        current = self.list_current()
        if not current or current[0].rules_sha256 != expected_rules_sha256:
            raise RuleAdminConflictError("active rule hash does not match")
        entry = current[0]
        retired = _retired_identities(self._root)
        retired.add((entry.rule_version, entry.rules_sha256))
        _atomic_json(
            self._root / "retired.json",
            {
                "schema_version": "1.0",
                "entries": [
                    {"rule_version": version, "rules_sha256": digest}
                    for version, digest in sorted(retired)
                ],
            },
        )
        _atomic_json(
            self._root / "active.json",
            {"schema_version": "1.0", "active": None},
        )
        return RuleAdminSummary(
            **{
                field: getattr(entry, field)
                for field in entry.__dataclass_fields__
                if field != "lifecycle"
            },
            lifecycle="retired",
        )

    def restore(
        self, version: str, expected_rules_sha256: str
    ) -> RuleAdminSummary:
        target = self._package("versions", version)
        selected = self._summary(target, "history")
        if selected.rules_sha256 != expected_rules_sha256:
            raise RuleAdminConflictError("selected rule hash does not match")
        retired = _retired_identities(self._root)
        retired.discard((version, expected_rules_sha256))
        _atomic_json(
            self._root / "retired.json",
            {
                "schema_version": "1.0",
                "entries": [
                    {"rule_version": item_version, "rules_sha256": digest}
                    for item_version, digest in sorted(retired)
                ],
            },
        )
        _atomic_json(
            self._root / "active.json",
            {
                "schema_version": "1.0",
                "active": {
                    "rule_version": version,
                    "rules_sha256": expected_rules_sha256,
                },
            },
        )
        return self._summary(target, "current")

    def copy_history_to_draft(
        self,
        source_version: str,
        source_expected_hash: str,
        new_version: str,
    ) -> RuleAdminSummary:
        active = _read_pointer(self._root)
        if active is not None and active["rule_version"] == source_version:
            raise RuleAdminConflictError("current rules are not history")
        source = self._package("versions", source_version)
        summary = self._summary(source, "history")
        if summary.package_hash != source_expected_hash:
            raise RuleAdminConflictError("source package hash does not match")
        manifest = json.loads(
            (source / "rule-package.json").read_text(encoding="utf-8")
        )
        manifest["rule_version"] = new_version
        manifest["package_id"] = f"{manifest['package_id']}-{new_version}"
        return self.create_draft(
            manifest,
            (source / "rules.yaml").read_text(encoding="utf-8"),
        )

    def preview_draft(
        self, version: str, summaries: tuple[Path, ...]
    ) -> RulePreview:
        snapshot = self._load(self._package("drafts", version))
        matched_batches = decisions = pending = total = 0
        for source in summaries:
            historical = StandardSummaryReader().read(source)
            for batch in historical.batches:
                total += 1
                evaluation = evaluate_rules(batch.record, snapshot)
                decisions += len(evaluation.decisions)
                pending += len(evaluation.pending_matches)
                if evaluation.decisions or evaluation.pending_matches:
                    matched_batches += 1
        return RulePreview(
            batch_count=total,
            matched_batch_count=matched_batches,
            decision_count=decisions,
            pending_match_count=pending,
            warnings=_warnings(snapshot.definitions),
        )

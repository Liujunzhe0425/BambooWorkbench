"""Read-only adapter for module-bundled, approved structured experience."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from moisture.adapters.experience.scope_matcher import (
    match_experience_scope,
    normalize_scope_value,
)
from moisture.ports.experience_repository import (
    EXPERIENCE_ID_PATTERN,
    SEMVER_PATTERN,
    ExperienceMetadata,
    ExperienceQuery,
    ExperienceReference,
)
from moisture.runtime_paths import module_root
from yaml.constructor import ConstructorError

_SAFE_ID = re.compile(EXPERIENCE_ID_PATTERN)
_SEMVER = re.compile(SEMVER_PATTERN)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExperienceRepositoryError(RuntimeError):
    """Base error for governed experience repository failures."""


class ExperienceValidationError(ExperienceRepositoryError):
    """An experience entry or manifest violates its contract."""


class ExperienceConflictError(ExperienceRepositoryError):
    """Two active approved entries are ambiguous."""


class ExperienceSecurityError(ExperienceRepositoryError):
    """A configured path can escape the approved experience root."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing front matter",
                node.start_mark,
                f"duplicate key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExperienceValidationError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _semver_key(version: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    precedence = version.split("+", maxsplit=1)[0]
    core, separator, prerelease = precedence.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    identifiers: tuple[tuple[int, int | str], ...] = ()
    if separator:
        identifiers = tuple(
            (0, int(item)) if item.isdigit() else (1, item)
            for item in prerelease.split(".")
        )
    return major, minor, patch, 0 if separator else 1, identifiers


def _is_reparse_point(path: Path) -> bool:
    linked = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(linked, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _quoted(body: str) -> str:
    return "\n".join(f"> {line}" for line in body.splitlines())


def _canonical_scope(metadata: ExperienceMetadata) -> tuple[tuple[str, ...], ...]:
    canonical: list[tuple[str, ...]] = []
    for values in (
        metadata.applicable_suppliers,
        metadata.applicable_materials,
        metadata.applicable_seasons,
        metadata.applicable_metrics,
    ):
        normalized = {normalize_scope_value(value) for value in values}
        canonical.append(("*",) if "*" in normalized else tuple(sorted(normalized)))
    return tuple(canonical)


def _scopes_overlap(first: ExperienceMetadata, second: ExperienceMetadata) -> bool:
    for first_values, second_values in zip(
        _canonical_scope(first), _canonical_scope(second), strict=True
    ):
        if "*" in first_values or "*" in second_values:
            continue
        if set(first_values).isdisjoint(second_values):
            return False
    return True


class LocalApprovedExperienceRepository:
    def __init__(self, root: Path, *, as_of: datetime | None = None) -> None:
        configured = Path(root)
        try:
            if _is_reparse_point(configured):
                raise ExperienceSecurityError("experience root must not be a link or reparse point")
            resolved = configured.resolve(strict=True)
        except ExperienceSecurityError:
            raise
        except OSError as error:
            raise ExperienceSecurityError("experience root does not exist") from error
        if not resolved.is_dir():
            raise ExperienceSecurityError("experience root must be a directory")
        self._root = resolved
        self._approved_root = resolved / "approved"
        self._as_of = as_of or datetime.now(UTC)
        if self._as_of.tzinfo is None or self._as_of.utcoffset() is None:
            raise ValueError("repository as_of must include a timezone")

    def search(self, context: ExperienceQuery) -> list[ExperienceReference]:
        as_of = context.as_of or self._as_of
        references = self._load_approved(as_of)
        matched: list[ExperienceReference] = []
        for reference in references:
            scope_match = match_experience_scope(reference, context)
            if scope_match is not None:
                matched.append(
                    replace(
                        reference,
                        match_reasons=scope_match.reasons,
                        exact_match_count=scope_match.exact_match_count,
                    )
                )
        matched.sort(key=lambda item: item.content_hash)
        matched.sort(key=lambda item: _semver_key(item.version), reverse=True)
        matched.sort(key=lambda item: normalize_scope_value(item.experience_id))
        matched.sort(key=lambda item: item.exact_match_count, reverse=True)
        return matched

    def list_approved(self) -> list[ExperienceReference]:
        """Return the current immutable, effective approved projection."""

        return self._load_approved(self._as_of)

    def get(self, experience_id: str, version: str) -> ExperienceReference | None:
        if _SAFE_ID.fullmatch(experience_id) is None:
            raise ValueError("invalid experience_id")
        if _SEMVER.fullmatch(version) is None:
            raise ValueError("invalid semantic version")
        for reference in self.list_approved():
            if reference.experience_id == experience_id and reference.version == version:
                return reference
        return None

    def _load_approved(self, as_of: datetime) -> list[ExperienceReference]:
        entries = self._load_manifest()
        validator = self._load_schema()
        loaded = [self._read_entry(path, digest, validator) for path, digest in entries]
        self._validate_governance(loaded)
        active = [
            entry.as_approved_reference()
            for entry in loaded
            if entry.metadata.status == "approved" and entry.metadata.effective_at <= as_of
        ]
        self._reject_conflicts(active)
        return active

    def _load_manifest(self) -> list[tuple[Path, str]]:
        path = self._root / "manifest.json"
        if not path.is_file() or _is_reparse_point(path):
            raise ExperienceSecurityError("manifest.json must be a regular local file")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json)
        except ExperienceRepositoryError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ExperienceValidationError("invalid experience manifest") from error
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "entries"}:
            raise ExperienceValidationError("manifest must contain schema_version and entries")
        if payload["schema_version"] != "1.0" or not isinstance(payload["entries"], list):
            raise ExperienceValidationError("unsupported experience manifest")
        result: list[tuple[Path, str]] = []
        seen: set[str] = set()
        for item in payload["entries"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise ExperienceValidationError("invalid manifest entry")
            relative_text, digest = item["path"], item["sha256"]
            if not isinstance(relative_text, str) or not isinstance(digest, str):
                raise ExperienceValidationError("manifest path and sha256 must be strings")
            relative = Path(relative_text)
            if (
                relative_text in seen
                or relative.is_absolute()
                or len(relative.parts) < 2
                or relative.parts[0] != "approved"
                or any(part in {"", ".", ".."} for part in relative.parts)
                or relative.suffix.casefold() != ".md"
            ):
                raise ExperienceSecurityError(
                    "manifest entry must be a unique approved Markdown path"
                )
            if _SHA256.fullmatch(digest) is None:
                raise ExperienceValidationError("manifest sha256 must be lowercase hexadecimal")
            seen.add(relative_text)
            result.append((relative, digest))
        return sorted(result, key=lambda item: item[0].as_posix())

    @staticmethod
    def _load_schema() -> Draft202012Validator:
        path = module_root() / "schemas" / "experience.schema.json"
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as error:
            raise ExperienceValidationError("invalid bundled experience schema") from error
        return Draft202012Validator(schema)

    def _read_entry(
        self, relative: Path, digest: str, validator: Draft202012Validator
    ) -> _LoadedEntry:
        path = self._root / relative
        try:
            approved = self._approved_root.resolve(strict=True)
            if _is_reparse_point(self._approved_root):
                raise ExperienceSecurityError(
                    "approved directory must not be a link or reparse point"
                )
            for parent in path.parents:
                if parent == self._root:
                    break
                if _is_reparse_point(parent):
                    raise ExperienceSecurityError(
                        "experience path contains a link or reparse point"
                    )
            if _is_reparse_point(path):
                raise ExperienceSecurityError(
                    "experience entry must not be a link or reparse point"
                )
            resolved = path.resolve(strict=True)
            if resolved.parent != approved and approved not in resolved.parents:
                raise ExperienceSecurityError("experience entry escapes approved root")
            content = self._read_regular_file(resolved)
        except ExperienceSecurityError:
            raise
        except OSError as error:
            raise ExperienceSecurityError("unable to securely read experience entry") from error
        actual_digest = hashlib.sha256(content).hexdigest()
        if actual_digest != digest:
            raise ExperienceValidationError("experience entry SHA-256 does not match manifest")
        try:
            text = content.decode("utf-8")
            payload, body = self._parse_front_matter(text)
            raw_effective_at = payload.get("effective_at")
            if isinstance(raw_effective_at, datetime):
                effective_at = raw_effective_at
            elif isinstance(raw_effective_at, str):
                effective_at = datetime.fromisoformat(
                    raw_effective_at.replace("Z", "+00:00")
                )
            else:
                raise ValueError("effective_at must be a date-time")
            schema_payload = {**payload, "effective_at": effective_at.isoformat()}
            validator.validate(schema_payload)
            metadata = ExperienceMetadata(
                **{
                    **schema_payload,
                    "effective_at": effective_at,
                    "applicable_suppliers": tuple(payload["applicable_suppliers"]),
                    "applicable_materials": tuple(payload["applicable_materials"]),
                    "applicable_seasons": tuple(payload["applicable_seasons"]),
                    "applicable_metrics": tuple(payload["applicable_metrics"]),
                    "evidence_sources": tuple(payload["evidence_sources"]),
                }
            )
        except Exception as error:
            raise ExperienceValidationError(
                f"invalid experience document: {relative.as_posix()}"
            ) from error
        return _LoadedEntry(
            metadata=metadata,
            body=body,
            digest=actual_digest,
            relative=relative,
        )

    @staticmethod
    def _read_regular_file(path: Path) -> bytes:
        descriptor = -1
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            opened = os.fstat(descriptor)
            linked = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(linked.st_mode):
                raise ExperienceSecurityError("experience entry must be a regular file")
            if (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino):
                raise ExperienceSecurityError("experience entry changed before secure read")
            with os.fdopen(descriptor, "rb", closefd=True) as source:
                descriptor = -1
                return source.read()
        except ExperienceSecurityError:
            raise
        except OSError as error:
            raise ExperienceSecurityError("unable to open experience entry securely") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ExperienceValidationError("experience document requires YAML front matter")
        try:
            closing = next(
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.strip() == "---"
            )
        except StopIteration as error:
            raise ExperienceValidationError("experience front matter is not closed") from error
        payload = yaml.load("\n".join(lines[1:closing]), Loader=_UniqueKeyLoader)
        if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
            raise ExperienceValidationError("experience front matter must be an object")
        return payload, "\n".join(lines[closing + 1 :]).strip()

    @staticmethod
    def _validate_governance(entries: list[_LoadedEntry]) -> None:
        versions: dict[tuple[str, str], ExperienceMetadata] = {}
        for entry in entries:
            reference = entry.metadata
            key = (reference.experience_id, reference.version)
            if key in versions:
                raise ExperienceConflictError(
                    "duplicate experience version: "
                    f"{reference.experience_id} {reference.version}"
                )
            versions[key] = reference
        for reference in versions.values():
            if reference.supersedes is not None:
                previous = versions.get((reference.experience_id, reference.supersedes))
                invalid_predecessor = previous is None or _semver_key(
                    previous.version
                ) >= _semver_key(reference.version)
                if invalid_predecessor:
                    raise ExperienceValidationError(
                        "supersedes must reference a real older version"
                    )

    @staticmethod
    def _reject_conflicts(references: list[ExperienceReference]) -> None:
        for index, first in enumerate(references):
            for second in references[index + 1 :]:
                same_id = first.experience_id == second.experience_id
                if same_id and _scopes_overlap(first, second):
                    raise ExperienceConflictError(
                        f"conflicting active experience: {first.experience_id}"
                    )


@dataclass(frozen=True, slots=True)
class _LoadedEntry:
    metadata: ExperienceMetadata
    body: str
    digest: str
    relative: Path

    def as_approved_reference(self) -> ExperienceReference:
        if self.metadata.status != "approved":
            raise ExperienceValidationError("inactive experience cannot affect review")
        return ExperienceReference(
            **asdict(self.metadata),
            quoted_reference=_quoted(self.body),
            content_hash=self.digest,
            reference_path=self.relative.as_posix(),
        )

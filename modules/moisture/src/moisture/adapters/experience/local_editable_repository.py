"""Offline editable experience store, isolated from the production runtime."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from moisture.adapters.experience.local_approved_repository import (
    LocalApprovedExperienceRepository,
    _is_reparse_point,
    _semver_key,
)
from moisture.ports.experience_admin_repository import (
    AdminExperience,
    AdminExperienceSummary,
)
from moisture.ports.experience_repository import (
    EXPERIENCE_ID_PATTERN,
    SEMVER_PATTERN,
    ExperienceMetadata,
)

_SAFE_ID = re.compile(EXPERIENCE_ID_PATTERN)
_SEMVER = re.compile(SEMVER_PATTERN)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATES = ("draft", "approved", "retired")


def _unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ExperienceAdminValidationError(f"duplicate manifest key: {key}")
        payload[key] = value
    return payload


class ExperienceAdminError(RuntimeError):
    pass


class ExperienceAdminValidationError(ExperienceAdminError):
    pass


class ExperienceAdminConflictError(ExperienceAdminError):
    pass


class ExperienceAdminSecurityError(ExperienceAdminError):
    pass


class LocalEditableExperienceRepository:
    """Single-user offline manager; production code must not import this adapter."""

    def __init__(self, root: Path) -> None:
        configured = Path(root)
        configured.mkdir(parents=True, exist_ok=True)
        try:
            if _is_reparse_point(configured):
                raise ExperienceAdminSecurityError("experience root must not be a link")
            self._root = configured.resolve(strict=True)
        except OSError as error:
            raise ExperienceAdminSecurityError("invalid experience root") from error
        for state in _STATES:
            directory = self._root / state
            directory.mkdir(exist_ok=True)
            if _is_reparse_point(directory):
                raise ExperienceAdminSecurityError("experience state directory must not be a link")
        manifest = self._root / "manifest.json"
        if manifest.is_symlink() or (manifest.exists() and _is_reparse_point(manifest)):
            raise ExperienceAdminSecurityError(
                "runtime manifest must not be a link or reparse point"
            )
        if not manifest.exists():
            self._atomic_write(manifest, self._manifest_bytes([]))
        self._load_manifest()

    def list(self) -> list[AdminExperience]:
        records: list[AdminExperience] = []
        for state in _STATES:
            directory = self._root / state
            for path in sorted(directory.glob("*.md")):
                self._guard_regular(path, directory)
                records.append(self._decode(path.read_bytes(), path.relative_to(self._root)))
        return sorted(records, key=lambda item: (item.experience_id, _semver_key(item.version)))

    def show(self, experience_id: str, version: str) -> AdminExperience:
        path = self._find(experience_id, version)
        return self._decode(path.read_bytes(), path.relative_to(self._root))

    def validate(self, document: str) -> AdminExperience:
        content = self._encode_text(document)
        return self._decode(content, Path("draft/validated.md"))

    def create(self, document: str) -> AdminExperience:
        content = self._encode_text(document)
        record = self._decode(content, Path("draft/pending.md"))
        if record.status != "draft":
            raise ExperienceAdminValidationError("new experience must be draft")
        if self._exists(record.experience_id, record.version):
            raise ExperienceAdminConflictError("experience ID/version already exists")
        self._validate_supersedes(record, document)
        target = self._path("draft", record.experience_id, record.version)
        self._atomic_write(target, content)
        return self._decode(content, target.relative_to(self._root))

    def update(
        self, experience_id: str, version: str, document: str, expected_hash: str
    ) -> AdminExperience:
        current_path = self._find(experience_id, version)
        current = self._decode(current_path.read_bytes(), current_path.relative_to(self._root))
        self._check_hash(current, expected_hash)
        if current.status != "draft":
            raise ExperienceAdminConflictError("approved or retired experience cannot be modified")
        content = self._encode_text(document)
        updated = self._decode(content, current_path.relative_to(self._root))
        if (updated.experience_id, updated.version, updated.status) != (
            experience_id,
            version,
            "draft",
        ):
            raise ExperienceAdminConflictError("update cannot change ID, version, or lifecycle")
        self._atomic_write(current_path, content)
        return self._decode(content, current_path.relative_to(self._root))

    def publish(self, experience_id: str, version: str, expected_hash: str) -> AdminExperience:
        source = self._find(experience_id, version)
        current = self._decode(source.read_bytes(), source.relative_to(self._root))
        self._check_hash(current, expected_hash)
        if current.status != "draft":
            raise ExperienceAdminConflictError("only draft experience can be published")
        entries = self._load_manifest()
        if any(
            self._decode((self._root / item["path"]).read_bytes(), Path(item["path"])).experience_id
            == experience_id
            for item in entries
        ):
            raise ExperienceAdminConflictError(
                "retire the active approved version before publishing a new version"
            )
        content = self._with_status(
            source.read_text(encoding="utf-8"), "approved", clear_supersedes=True
        )
        target = self._path("approved", experience_id, version)
        approved = self._decode(content, target.relative_to(self._root))
        entry = {"path": approved.path, "sha256": approved.sha256}
        self._transition(source, target, content, [*entries, entry])
        return approved

    def retire(self, experience_id: str, version: str, expected_hash: str) -> AdminExperience:
        source = self._find(experience_id, version)
        current = self._decode(source.read_bytes(), source.relative_to(self._root))
        self._check_hash(current, expected_hash)
        if current.status != "approved":
            raise ExperienceAdminConflictError("only approved experience can be retired")
        content = self._with_status(source.read_text(encoding="utf-8"), "retired")
        target = self._path("retired", experience_id, version)
        retired = self._decode(content, target.relative_to(self._root))
        entries = [item for item in self._load_manifest() if item["path"] != current.path]
        self._transition(source, target, content, entries)
        return retired

    # -- E-S1 three-pane queries --

    def list_drafts(self) -> list[AdminExperienceSummary]:
        return self._list_state_summary("draft")

    def list_approved(self) -> list[AdminExperienceSummary]:
        return self._list_state_summary("approved")

    def list_history(self) -> list[AdminExperienceSummary]:
        return self._list_state_summary("retired")

    def _list_state_summary(self, state: str) -> list[AdminExperienceSummary]:
        result: list[AdminExperienceSummary] = []
        directory = self._root / state
        if state == "approved":
            entries = self._load_manifest()
            manifest_paths = {item["path"] for item in entries}
            stored_paths = {
                path.relative_to(self._root).as_posix()
                for path in directory.rglob("*.md")
            }
            if stored_paths != manifest_paths:
                raise ExperienceAdminValidationError(
                    "approved storage does not match runtime manifest"
                )
            paths = [self._root / item["path"] for item in entries]
        else:
            paths = sorted(directory.glob("*.md"))
        for path in paths:
            if state == "approved":
                self._guard_manifest_entry(path)
            else:
                self._guard_regular(path, directory)
            admin = self._decode(path.read_bytes(), path.relative_to(self._root))
            text = path.read_text(encoding="utf-8")
            payload, _body = LocalApprovedExperienceRepository._parse_front_matter(text)
            result.append(
                AdminExperienceSummary(
                    experience_id=admin.experience_id,
                    version=admin.version,
                    status=admin.status,
                    title=str(payload.get("title", "")),
                    source=str(payload.get("source", "")),
                    sha256=admin.sha256,
                    effective_at=str(payload.get("effective_at", "")),
                    applicable_suppliers=", ".join(payload.get("applicable_suppliers", [])),
                    applicable_materials=", ".join(payload.get("applicable_materials", [])),
                    applicable_seasons=", ".join(payload.get("applicable_seasons", [])),
                    applicable_metrics=", ".join(payload.get("applicable_metrics", [])),
                    supersedes=str(payload.get("supersedes", "")),
                )
            )
        result.sort(key=lambda item: _semver_key(item.version), reverse=True)
        result.sort(key=lambda item: item.experience_id)
        return result

    # -- E-S1 history-copy --

    def copy_retired_to_draft(
        self,
        experience_id: str,
        source_version: str,
        source_expected_hash: str,
        new_version: str,
    ) -> AdminExperience:
        source_path = self._find(experience_id, source_version)
        source_bytes = source_path.read_bytes()
        current = self._decode(source_bytes, source_path.relative_to(self._root))
        self._check_hash(current, source_expected_hash)
        if current.status != "retired":
            raise ExperienceAdminConflictError(
                "only retired experience can be copied to draft"
            )
        new_path = self._path("draft", experience_id, new_version)
        if new_path.exists():
            raise ExperienceAdminConflictError(
                f"draft {experience_id} v{new_version} already exists"
            )
        source_text = source_bytes.decode("utf-8")
        payload, body = LocalApprovedExperienceRepository._parse_front_matter(source_text)
        payload["version"] = new_version
        payload["status"] = "draft"
        payload["supersedes"] = source_version
        payload.pop("published_at", None)
        payload.pop("retired_at", None)
        lines = [f"{key}: {value}" for key, value in payload.items()]
        new_doc = "---\n" + "\n".join(lines) + "\n---\n" + body
        return self.create(new_doc)

    def _transition(
        self, source: Path, target: Path, content: bytes, entries: list[dict[str, str]]
    ) -> None:
        if target.exists():
            raise ExperienceAdminConflictError("target lifecycle version already exists")
        source_content = source.read_bytes()
        manifest = self._root / "manifest.json"
        old_manifest = manifest.read_bytes()
        self._atomic_write(target, content)
        try:
            source.unlink()
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        try:
            self._atomic_write(manifest, self._manifest_bytes(entries))
        except BaseException:
            try:
                if not source.exists():
                    self._atomic_write(source, source_content)
                if manifest.read_bytes() != old_manifest:
                    self._atomic_write(manifest, old_manifest)
            finally:
                target.unlink(missing_ok=True)
            raise

    def _validate_supersedes(self, record: AdminExperience, document: str) -> None:
        payload, _ = LocalApprovedExperienceRepository._parse_front_matter(document)
        previous = payload.get("supersedes")
        if previous is None:
            return
        try:
            predecessor = self.show(record.experience_id, previous)
        except KeyError as error:
            raise ExperienceAdminValidationError(
                "supersedes must reference an existing version"
            ) from error
        if predecessor.status not in {"approved", "retired"} or _semver_key(
            previous
        ) >= _semver_key(record.version):
            raise ExperienceAdminValidationError("supersedes must reference older approved history")

    def _decode(self, content: bytes, relative: Path) -> AdminExperience:
        try:
            text = content.decode("utf-8")
            payload, body = LocalApprovedExperienceRepository._parse_front_matter(text)
            raw_time = payload.get("effective_at")
            effective_at = (
                raw_time
                if isinstance(raw_time, datetime)
                else datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            )
            normalized = {**payload, "effective_at": effective_at.isoformat()}
            validator = LocalApprovedExperienceRepository._load_schema()
            validator.validate(normalized)
            metadata = ExperienceMetadata(
                **{
                    **normalized,
                    "effective_at": effective_at,
                    "applicable_suppliers": tuple(payload["applicable_suppliers"]),
                    "applicable_materials": tuple(payload["applicable_materials"]),
                    "applicable_seasons": tuple(payload["applicable_seasons"]),
                    "applicable_metrics": tuple(payload["applicable_metrics"]),
                    "evidence_sources": tuple(payload["evidence_sources"]),
                }
            )
            if metadata.status not in _STATES:
                raise ValueError("unsupported lifecycle status")
        except Exception as error:
            raise ExperienceAdminValidationError("invalid experience document") from error
        if relative.parts and relative.parts[0] in _STATES and metadata.status != relative.parts[0]:
            raise ExperienceAdminValidationError(
                "document status does not match lifecycle directory"
            )
        return AdminExperience(
            metadata.experience_id,
            metadata.version,
            metadata.status,
            hashlib.sha256(content).hexdigest(),
            body,
            relative.as_posix(),
        )

    @staticmethod
    def _encode_text(document: str) -> bytes:
        if not isinstance(document, str):
            raise ExperienceAdminValidationError("document must be text")
        return document.encode("utf-8")

    @staticmethod
    def _with_status(document: str, status: str, *, clear_supersedes: bool = False) -> bytes:
        payload, body = LocalApprovedExperienceRepository._parse_front_matter(document)
        payload["status"] = status
        if clear_supersedes:
            # The T12 runtime manifest intentionally excludes retired history, while
            # its reader requires every supersedes target to be present in that same
            # manifest. The admin layer validates lineage before publication, then
            # removes this storage-only link from the active runtime projection.
            payload["supersedes"] = None
        rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        return f"---\n{rendered}---\n{body}\n".encode()

    def _path(self, state: str, experience_id: str, version: str) -> Path:
        self._validate_key(experience_id, version)
        return self._root / state / f"{experience_id}--{version}.md"

    def _find(self, experience_id: str, version: str) -> Path:
        self._validate_key(experience_id, version)
        existing: list[Path] = []
        for state in _STATES:
            directory = self._root / state
            for path in directory.glob("*.md"):
                self._guard_regular(path, directory)
                record = self._decode(path.read_bytes(), path.relative_to(self._root))
                if (record.experience_id, record.version) == (experience_id, version):
                    existing.append(path)
        if len(existing) != 1:
            if not existing:
                raise KeyError(f"experience not found: {experience_id} {version}")
            raise ExperienceAdminConflictError("duplicate lifecycle version")
        self._guard_regular(existing[0], existing[0].parent)
        return existing[0]

    def _exists(self, experience_id: str, version: str) -> bool:
        try:
            self._find(experience_id, version)
        except KeyError:
            return False
        return True

    @staticmethod
    def _validate_key(experience_id: str, version: str) -> None:
        if _SAFE_ID.fullmatch(experience_id) is None or _SEMVER.fullmatch(version) is None:
            raise ExperienceAdminSecurityError("invalid experience ID or version")

    @staticmethod
    def _check_hash(record: AdminExperience, expected_hash: str) -> None:
        if _SHA256.fullmatch(expected_hash) is None or record.sha256 != expected_hash:
            raise ExperienceAdminConflictError("expected hash does not match current content")

    @staticmethod
    def _guard_regular(path: Path, parent: Path) -> None:
        try:
            if _is_reparse_point(parent) or _is_reparse_point(path):
                raise ExperienceAdminSecurityError("links and reparse points are forbidden")
            resolved_parent = parent.resolve(strict=True)
            resolved = path.resolve(strict=True)
            linked = path.stat(follow_symlinks=False)
            if resolved.parent != resolved_parent or not stat.S_ISREG(linked.st_mode):
                raise ExperienceAdminSecurityError("experience path escapes lifecycle directory")
        except ExperienceAdminSecurityError:
            raise
        except OSError as error:
            raise ExperienceAdminSecurityError("experience path cannot be read safely") from error

    def _guard_manifest_entry(self, path: Path) -> None:
        approved = self._root / "approved"
        try:
            if _is_reparse_point(approved):
                raise ExperienceAdminSecurityError("approved directory must not be a link")
            resolved_approved = approved.resolve(strict=True)
            for parent in path.parents:
                if parent == self._root:
                    break
                if _is_reparse_point(parent):
                    raise ExperienceAdminSecurityError("runtime manifest path contains a link")
            if _is_reparse_point(path):
                raise ExperienceAdminSecurityError("runtime manifest entry must not be a link")
            resolved = path.resolve(strict=True)
            linked = path.stat(follow_symlinks=False)
            if resolved_approved not in resolved.parents or not stat.S_ISREG(linked.st_mode):
                raise ExperienceAdminSecurityError("runtime manifest entry escapes approved")
        except ExperienceAdminSecurityError:
            raise
        except OSError as error:
            raise ExperienceAdminSecurityError(
                "runtime manifest entry cannot be read safely"
            ) from error

    def _load_manifest(self) -> list[dict[str, str]]:
        manifest = self._root / "manifest.json"
        try:
            self._guard_regular(manifest, self._root)
            payload = json.loads(
                manifest.read_text(encoding="utf-8"), object_pairs_hook=_unique_json
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ExperienceAdminValidationError("invalid runtime manifest") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "entries"}
            or payload["schema_version"] != "1.0"
            or not isinstance(payload["entries"], list)
        ):
            raise ExperienceAdminValidationError("invalid runtime manifest")
        entries: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in payload["entries"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise ExperienceAdminValidationError("invalid runtime manifest entry")
            relative_text = item["path"]
            digest = item["sha256"]
            if not isinstance(relative_text, str) or not isinstance(digest, str):
                raise ExperienceAdminValidationError("invalid runtime manifest entry")
            relative = Path(relative_text)
            if (
                relative_text in seen
                or relative.is_absolute()
                or len(relative.parts) < 2
                or relative.parts[0] != "approved"
                or any(part in {"", ".", ".."} for part in relative.parts)
                or relative.suffix.casefold() != ".md"
            ):
                raise ExperienceAdminSecurityError("unsafe runtime manifest path")
            if _SHA256.fullmatch(digest) is None:
                raise ExperienceAdminValidationError("invalid runtime manifest SHA-256")
            entry_path = self._root / relative
            self._guard_manifest_entry(entry_path)
            content = entry_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ExperienceAdminValidationError("runtime manifest hash mismatch")
            if self._decode(content, relative).status != "approved":
                raise ExperienceAdminValidationError(
                    "runtime manifest may contain only approved experience"
                )
            seen.add(relative_text)
            entries.append({"path": relative.as_posix(), "sha256": digest})
        return entries

    @staticmethod
    def _manifest_bytes(entries: list[dict[str, str]]) -> bytes:
        ordered = sorted(entries, key=lambda item: item["path"])
        return (
            json.dumps({"schema_version": "1.0", "entries": ordered}, ensure_ascii=False, indent=2)
            + "\n"
        ).encode("utf-8")

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> None:
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

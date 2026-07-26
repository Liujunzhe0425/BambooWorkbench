"""Private immutable contract for one finalized moisture month."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from moisture.runtime_paths import module_root

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SNAPSHOT_SCHEMA = "moisture-monthly-snapshot.schema.json"


class MonthlySnapshotError(ValueError):
    """Stable, sanitized error raised by the private monthly snapshot contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_INVALID",
            "monthly snapshot payload must be an object",
        )
    return decoded


def _load_schema() -> dict[str, Any]:
    try:
        payload = json.loads((module_root() / "schemas" / _SNAPSHOT_SCHEMA).read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_SCHEMA_UNAVAILABLE",
            "monthly snapshot schema is unavailable",
        ) from error
    if not isinstance(payload, dict):
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_SCHEMA_UNAVAILABLE",
            "monthly snapshot schema is unavailable",
        )
    return payload


def validate_monthly_snapshot_payload(payload: object) -> None:
    """Validate the private payload without exposing schema internals or input data."""

    try:
        schema = _load_schema()
        Draft202012Validator.check_schema(schema)
        error = next(
            iter(
                Draft202012Validator(
                    schema,
                    format_checker=FormatChecker(),
                ).iter_errors(payload)
            ),
            None,
        )
    except SchemaError as failure:
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_SCHEMA_UNAVAILABLE",
            "monthly snapshot schema is unavailable",
        ) from failure
    if error is not None:
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_INVALID",
            "monthly snapshot payload is invalid",
        )


@dataclass(frozen=True, slots=True)
class MonthlySnapshotRecord:
    """One immutable record stored as canonical private JSON."""

    _canonical_json: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> MonthlySnapshotRecord:
        canonical = json.dumps(
            _canonical_mapping(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cls(canonical)

    @property
    def record_id(self) -> str:
        return str(self.to_payload()["record_id"])

    def to_payload(self) -> dict[str, Any]:
        payload = json.loads(self._canonical_json)
        if not isinstance(payload, dict):  # pragma: no cover - frozen constructor invariant
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot record is invalid",
            )
        return payload


@dataclass(frozen=True, slots=True)
class MonthlySnapshot:
    """A deterministic, immutable snapshot of one finalized business month."""

    module_version: str
    year: int
    month: int
    rule_version: str
    rule_sha256: str
    records: tuple[MonthlySnapshotRecord, ...]
    schema_version: str = "1.0"
    module_id: str = "moisture"

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        if self.schema_version != "1.0" or self.module_id != "moisture":
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot identity is invalid",
            )
        if not _VERSION.fullmatch(self.module_version):
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "module version is invalid",
            )
        if not 1000 <= self.year <= 9999 or not 1 <= self.month <= 12:
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot period is invalid",
            )
        if not _VERSION.fullmatch(self.rule_version) or not _SHA256.fullmatch(
            self.rule_sha256
        ):
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_RULE_IDENTITY_INVALID",
                "monthly snapshot rule identity is invalid",
            )
        record_ids = [record.record_id for record in self.records]
        if not record_ids or len(record_ids) != len(set(record_ids)):
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot records must be non-empty and unique",
            )
        semantic_keys: list[tuple[str, str, str]] = []
        try:
            for record in self.records:
                payload = record.to_payload()
                effective_date = payload["test_date"] or payload["arrival_date"]
                if (
                    not isinstance(effective_date, str)
                    or effective_date[:7] != f"{self.year:04d}-{self.month:02d}"
                ):
                    raise MonthlySnapshotError(
                        "MONTHLY_SNAPSHOT_INVALID",
                        "monthly snapshot record period is invalid",
                    )
                traceability = payload["traceability"]
                if (
                    not isinstance(traceability, Mapping)
                    or traceability["rule_version"] != self.rule_version
                    or traceability["rule_sha256"] != self.rule_sha256
                ):
                    raise MonthlySnapshotError(
                        "MONTHLY_SNAPSHOT_RULE_IDENTITY_INVALID",
                        "monthly snapshot record rule identity is invalid",
                    )
                semantic_keys.append(
                    (
                        effective_date,
                        str(payload["record_id"]),
                        str(payload["business_fingerprint"]),
                    )
                )
        except (KeyError, TypeError) as error:
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot record is invalid",
            ) from error
        if semantic_keys != sorted(semantic_keys):
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot records are not in stable order",
            )

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "period": {"year": self.year, "month": self.month},
            "rule_snapshot": {
                "version": self.rule_version,
                "sha256": self.rule_sha256,
            },
            "records": [record.to_payload() for record in self.records],
        }
        canonical = _canonical_mapping(payload)
        validate_monthly_snapshot_payload(canonical)
        return canonical

    @classmethod
    def from_payload(cls, payload: object) -> MonthlySnapshot:
        validate_monthly_snapshot_payload(payload)
        if not isinstance(payload, Mapping):  # narrowed by schema
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot payload must be an object",
            )
        period = payload["period"]
        rule = payload["rule_snapshot"]
        records = payload["records"]
        if not isinstance(period, Mapping) or not isinstance(rule, Mapping):
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot payload is invalid",
            )
        if not isinstance(records, list):
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_INVALID",
                "monthly snapshot records are invalid",
            )
        return cls(
            schema_version=str(payload["schema_version"]),
            module_id=str(payload["module_id"]),
            module_version=str(payload["module_version"]),
            year=int(period["year"]),
            month=int(period["month"]),
            rule_version=str(rule["version"]),
            rule_sha256=str(rule["sha256"]),
            records=tuple(
                MonthlySnapshotRecord.from_payload(record)
                for record in records
                if isinstance(record, Mapping)
            ),
        )


def canonical_snapshot_bytes(snapshot: MonthlySnapshot) -> bytes:
    """Return the exact deterministic UTF-8 representation written to disk."""

    return (
        json.dumps(
            snapshot.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def write_monthly_snapshot(snapshot: MonthlySnapshot, output_dir: Path) -> Path:
    """Atomically publish the private snapshot inside an authorized output directory."""

    if not output_dir.is_absolute():
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_WRITE_FAILED",
            "monthly snapshot output directory must be absolute",
        )
    destination = output_dir / "moisture-monthly-snapshot.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".moisture-monthly-snapshot.",
            suffix=".tmp",
            dir=output_dir,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(canonical_snapshot_bytes(snapshot))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception as error:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        if isinstance(error, MonthlySnapshotError):
            raise
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_WRITE_FAILED",
            "monthly snapshot could not be written",
        ) from error
    return destination

"""Private request and response models for offline monthly rollup rendering."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class MonthlyRollupError(ValueError):
    """Stable, sanitized error raised by the private rollup contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class MonthlySnapshotReference:
    """One framework-authorized monthly snapshot input."""

    month: int
    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly snapshot reference month is invalid",
            )
        if not self.path.is_absolute() or not _SHA256.fullmatch(self.sha256):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly snapshot reference is invalid",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "month": self.month,
            "path": str(self.path),
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class MonthlyRollupRequest:
    """Module-private request frozen before the framework publishes its envelope."""

    year: int
    month: int
    snapshot_root: Path
    output_dir: Path
    business_config_version: str
    business_config_sha256: str
    snapshots: tuple[MonthlySnapshotReference, ...]
    network_allowed: bool = False
    schema_version: str = "1.0"
    module_id: str = "moisture"

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshots", tuple(self.snapshots))
        if self.schema_version != "1.0":
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup schema version is invalid",
            )
        if self.module_id != "moisture":
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_MODULE_MISMATCH",
                "monthly rollup request is intended for a different module",
            )
        if not 1000 <= self.year <= 9999 or not 1 <= self.month <= 12:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup target period is invalid",
            )
        if self.network_allowed:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_OFFLINE_VIOLATION",
                "monthly rollup must run offline",
            )
        if not self.snapshot_root.is_absolute() or not self.output_dir.is_absolute():
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_OUTPUT_PATH_INVALID",
                "monthly rollup paths must be absolute",
            )
        if not _VERSION.fullmatch(self.business_config_version) or not _SHA256.fullmatch(
            self.business_config_sha256
        ):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup business configuration identity is invalid",
            )
        months = [reference.month for reference in self.snapshots]
        if not months:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup requires at least one snapshot",
            )
        if len(months) != len(set(months)):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_DUPLICATE_MONTH",
                "monthly rollup contains a duplicate month",
            )
        if months != sorted(months):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_MONTH_ORDER_INVALID",
                "monthly rollup snapshots are not ordered by month",
            )
        if any(snapshot_month > self.month for snapshot_month in months):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_MONTH_AFTER_TARGET",
                "monthly rollup contains a snapshot after the target month",
            )
        if months[-1] != self.month:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup must include the target month snapshot",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "module_id": self.module_id,
            "target_period": {"year": self.year, "month": self.month},
            "snapshot_root": str(self.snapshot_root),
            "output_dir": str(self.output_dir),
            "network_allowed": self.network_allowed,
            "business_config": {
                "version": self.business_config_version,
                "sha256": self.business_config_sha256,
            },
            "snapshots": [snapshot.to_payload() for snapshot in self.snapshots],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> MonthlyRollupRequest:
        try:
            target = payload["target_period"]
            config = payload["business_config"]
            snapshots = payload["snapshots"]
            if (
                not isinstance(target, Mapping)
                or not isinstance(config, Mapping)
                or not isinstance(snapshots, list)
                or any(not isinstance(item, Mapping) for item in snapshots)
                or not isinstance(payload["network_allowed"], bool)
            ):
                raise TypeError
            return cls(
                schema_version=str(payload["schema_version"]),
                module_id=str(payload["module_id"]),
                year=int(target["year"]),
                month=int(target["month"]),
                snapshot_root=Path(str(payload["snapshot_root"])),
                output_dir=Path(str(payload["output_dir"])),
                network_allowed=payload["network_allowed"],
                business_config_version=str(config["version"]),
                business_config_sha256=str(config["sha256"]),
                snapshots=tuple(
                    MonthlySnapshotReference(
                        month=int(item["month"]),
                        path=Path(str(item["path"])),
                        sha256=str(item["sha256"]),
                    )
                    for item in snapshots
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, MonthlyRollupError):
                raise
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup request is invalid",
            ) from error


@dataclass(frozen=True, slots=True)
class MonthlyRollupArtifact:
    path: str
    type: str
    label: str
    mime_type: str
    sha256: str

    def __post_init__(self) -> None:
        relative = PurePosixPath(self.path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in self.path
            or not self.path
            or not _SHA256.fullmatch(self.sha256)
        ):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_ARTIFACT_WRITE_FAILED",
                "monthly rollup artifact metadata is invalid",
            )

    def to_payload(self) -> dict[str, str]:
        return {
            "path": self.path,
            "type": self.type,
            "label": self.label,
            "mime_type": self.mime_type,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class MonthlyRollupResult:
    year: int
    month: int
    used_months: tuple[int, ...]
    snapshot_hashes: tuple[tuple[int, str], ...]
    record_count: int
    artifacts: tuple[MonthlyRollupArtifact, ...]
    schema_version: str = "1.0"
    module_id: str = "moisture"
    status: str = "success"

    def __post_init__(self) -> None:
        object.__setattr__(self, "used_months", tuple(self.used_months))
        object.__setattr__(self, "snapshot_hashes", tuple(self.snapshot_hashes))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        snapshot_months = [month for month, _digest in self.snapshot_hashes]
        if (
            self.schema_version != "1.0"
            or self.module_id != "moisture"
            or self.status != "success"
            or not 1000 <= self.year <= 9999
            or not 1 <= self.month <= 12
            or self.record_count < 1
            or not self.artifacts
            or not self.used_months
            or list(self.used_months) != sorted(set(self.used_months))
            or any(not 1 <= used_month <= 12 for used_month in self.used_months)
            or any(used_month > self.month for used_month in self.used_months)
            or snapshot_months != list(self.used_months)
            or any(not _SHA256.fullmatch(digest) for _month, digest in self.snapshot_hashes)
        ):
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup result is invalid",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "module_id": self.module_id,
            "status": self.status,
            "target_period": {"year": self.year, "month": self.month},
            "used_months": list(self.used_months),
            "snapshot_hashes": [
                {"month": month, "sha256": digest}
                for month, digest in self.snapshot_hashes
            ],
            "record_count": self.record_count,
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
        }

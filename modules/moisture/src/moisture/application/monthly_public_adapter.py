"""Thin adapter between the framework v1.3 envelope and private rollup core."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from moisture import __version__
from moisture.application.monthly_rollup import render_monthly_rollup
from moisture.contract.monthly_rollup import (
    MonthlyRollupError,
    MonthlyRollupRequest,
    MonthlySnapshotReference,
)
from moisture.contract.monthly_snapshot import MonthlySnapshot, MonthlySnapshotError
from moisture.contract.progress import emit_progress
from moisture.infrastructure.atomic_write import write_json_atomic
from moisture.runtime_paths import module_root

_REQUEST_SCHEMA = "moisture-monthly-rollup-public-request.schema.json"
_RESPONSE_SCHEMA = "moisture-monthly-rollup-public-response.schema.json"


def _schema(name: str) -> dict[str, Any]:
    try:
        payload = json.loads((module_root() / "schemas" / name).read_text("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError
        Draft202012Validator.check_schema(payload)
        return payload
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError, TypeError) as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SCHEMA_UNAVAILABLE",
            "monthly rollup public schema is unavailable",
        ) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_request(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or not path.is_file():
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_REQUEST_INVALID",
            "monthly rollup request path is invalid",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator(_schema(_REQUEST_SCHEMA)).validate(payload)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_REQUEST_INVALID",
            "monthly rollup public request is invalid",
        ) from error
    if not isinstance(payload, dict):  # schema narrows; keeps static callers safe
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_REQUEST_INVALID",
            "monthly rollup public request is invalid",
        )
    if payload["module_id"] != "moisture" or payload["module_version"] != __version__:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_MODULE_MISMATCH",
            "monthly rollup request identity does not match this module",
        )
    if payload.get("offline_required", True) is not True:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_OFFLINE_VIOLATION",
            "monthly rollup must be explicitly offline",
        )
    if os.environ.get("BAMBOO_OFFLINE") != "1":
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_OFFLINE_VIOLATION",
            "monthly rollup requires the framework offline environment",
        )
    return payload


def _snapshot_rule_identity(snapshot_path: Path) -> tuple[str, str]:
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot = MonthlySnapshot.from_payload(payload)
        return snapshot.rule_version, snapshot.rule_sha256
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        MonthlySnapshotError,
    ) as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
            "monthly rollup snapshot payload is invalid",
        ) from error


def _private_request(payload: Mapping[str, Any]) -> MonthlyRollupRequest:
    public_snapshots = payload["snapshots"]
    if not isinstance(public_snapshots, list):  # schema invariant
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_REQUEST_INVALID",
            "monthly rollup snapshots are invalid",
        )
    references: list[MonthlySnapshotReference] = []
    for item in public_snapshots:
        if not isinstance(item, Mapping):  # schema invariant
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_REQUEST_INVALID",
                "monthly rollup snapshot reference is invalid",
            )
        path = Path(str(item["path"]))
        try:
            if path.stat().st_size != int(item["size"]) or _sha256(path) != item["sha256"]:
                raise MonthlyRollupError(
                    "MONTHLY_ROLLUP_SNAPSHOT_HASH_MISMATCH",
                    "monthly rollup snapshot integrity does not match",
                )
        except OSError as error:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
                "monthly rollup snapshot is unavailable",
            ) from error
        references.append(
            MonthlySnapshotReference(
                month=int(item["month"]),
                path=path,
                sha256=str(item["sha256"]),
            )
        )

    identity = payload.get("configuration_identity")
    if identity is None:
        version, digest = _snapshot_rule_identity(references[-1].path)
    elif isinstance(identity, Mapping):
        version, digest = str(identity["version"]), str(identity["sha256"])
    else:  # schema invariant
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_REQUEST_INVALID",
            "monthly rollup configuration identity is invalid",
        )
    return MonthlyRollupRequest(
        year=int(payload["year"]),
        month=int(payload["target_month"]),
        snapshot_root=Path(str(payload["snapshot_root"])),
        output_dir=Path(str(payload["output_dir"])),
        business_config_version=version,
        business_config_sha256=digest,
        snapshots=tuple(references),
        network_allowed=False,
    )


def _snapshot_acknowledgements(payload: Mapping[str, Any]) -> list[dict[str, object]]:
    snapshots = payload["snapshots"]
    if not isinstance(snapshots, list):  # schema invariant
        return []
    return [
        {
            "snapshot_id": str(item["snapshot_id"]),
            "month": int(item["month"]),
            "sha256": str(item["sha256"]),
        }
        for item in snapshots
        if isinstance(item, Mapping)
    ]


def _base_response(payload: Mapping[str, Any]) -> dict[str, object]:
    snapshots = payload["snapshots"]
    return {
        "schema_version": "1.0",
        "transaction_id": str(payload["transaction_id"]),
        "module_id": "moisture",
        "module_version": __version__,
        "year": int(payload["year"]),
        "target_month": int(payload["target_month"]),
        "used_months": [
            int(item["month"])
            for item in snapshots
            if isinstance(item, Mapping)
        ],
        "snapshot_hashes": _snapshot_acknowledgements(payload),
        "record_count": 0,
        "outputs": [],
        "network_call_count": 0,
    }


def _validate_response(payload: dict[str, object]) -> None:
    try:
        Draft202012Validator(_schema(_RESPONSE_SCHEMA)).validate(payload)
    except ValidationError as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_RESPONSE_INVALID",
            "monthly rollup public response is invalid",
        ) from error


def _response_path(response_path: Path, output_dir: Path) -> Path:
    if (
        not response_path.is_absolute()
        or response_path.name != "rollup-result.json"
        or response_path.parent.resolve() != output_dir.resolve()
    ):
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_OUTPUT_PATH_INVALID",
            "monthly rollup response path is outside output_dir",
        )
    return response_path


def _write_failure(
    request: Mapping[str, Any],
    response_path: Path,
    error: MonthlyRollupError,
) -> None:
    payload = _base_response(request)
    payload.update(
        {
            "status": "failed",
            "error": {
                "code": error.code.lower(),
                "message": str(error)[:300],
            },
        }
    )
    _validate_response(payload)
    write_json_atomic(response_path, payload)


def run_public_monthly_rollup(request_path: Path, response_path: Path) -> int:
    """Run the approved process contract without exposing private DTOs."""

    try:
        public_request = _read_request(request_path)
        output_dir = Path(str(public_request["output_dir"]))
        trusted_response = _response_path(response_path, output_dir)
        private_request = _private_request(public_request)
    except MonthlyRollupError as error:
        sys.stderr.write(f"moisture rollup: {error.code.lower()}\n")
        return 2

    emit_progress(0, "Monthly rollup started")
    try:
        private_result = render_monthly_rollup(private_request)
        response = _base_response(public_request)
        response.update(
            {
                "status": "success",
                "used_months": list(private_result.used_months),
                "record_count": private_result.record_count,
                "outputs": [
                    {
                        **artifact.to_payload(),
                        "path": str((private_request.output_dir / artifact.path).resolve()),
                    }
                    for artifact in private_result.artifacts
                ],
                "error": None,
            }
        )
        _validate_response(response)
        write_json_atomic(trusted_response, response)
    except MonthlyRollupError as error:
        try:
            _write_failure(public_request, trusted_response, error)
        except Exception:
            sys.stderr.write("moisture rollup: response_write_failed\n")
            return 4
        sys.stderr.write(f"moisture rollup: {error.code.lower()}\n")
        return 3
    except Exception:
        error = MonthlyRollupError(
            "MONTHLY_ROLLUP_INTERNAL_ERROR",
            "monthly rollup could not be completed",
        )
        try:
            _write_failure(public_request, trusted_response, error)
        except Exception:
            sys.stderr.write("moisture rollup: response_write_failed\n")
            return 4
        sys.stderr.write("moisture rollup: monthly_rollup_internal_error\n")
        return 4
    emit_progress(100, "Monthly rollup completed")
    return 0

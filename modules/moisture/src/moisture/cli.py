"""Command-line contract surface for the moisture module."""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from moisture import __version__
from moisture.contract.bootstrap_result import build_bootstrap_result
from moisture.contract.progress import emit_progress
from moisture.infrastructure.atomic_write import write_json_atomic
from moisture.infrastructure.diagnostics import collect_runtime_issues

_ALLOWED_JOB_FIELDS = {
    "schema_version",
    "job_id",
    "module_id",
    "phase",
    "run_mode",
    "input_files",
    "output_dir",
    "module_config_file",
    "ai_enabled",
    "allowed_knowledge_scopes",
    "parent_job_id",
    "confirmation_file",
    "service_response_file",
}
_REQUIRED_JOB_FIELDS = {
    "schema_version",
    "job_id",
    "module_id",
    "phase",
    "run_mode",
    "input_files",
    "output_dir",
}
_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{6,64}$")


class JobValidationError(ValueError):
    """A stable, user-facing bootstrap job contract error."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moisture", add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", add_help=False)
    commands.add_parser("self-check", add_help=False)
    run_parser = commands.add_parser("run", add_help=False)
    run_parser.add_argument("--job", required=True)
    return parser


def _require_type(payload: dict[str, Any], field: str, expected: type[Any]) -> Any:
    value = payload.get(field)
    if type(value) is not expected:
        raise JobValidationError(f"{field} has an invalid type")
    return value


def _validate_optional_path(payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if value is None:
        return
    if not isinstance(value, str) or not PureWindowsPath(value).is_absolute():
        raise JobValidationError(f"{field} must be an absolute Windows path or null")


def _load_job(job_path: Path) -> dict[str, Any]:
    if not job_path.is_absolute():
        raise JobValidationError("--job must be an absolute path")
    if not job_path.is_file():
        raise JobValidationError("job file does not exist")
    try:
        payload = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JobValidationError("job file is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise JobValidationError("job JSON must be an object")

    unexpected = sorted(set(payload) - _ALLOWED_JOB_FIELDS)
    if unexpected:
        raise JobValidationError(f"unexpected job fields: {', '.join(unexpected)}")
    missing = sorted(_REQUIRED_JOB_FIELDS - set(payload))
    if missing:
        raise JobValidationError(f"missing job fields: {', '.join(missing)}")

    if _require_type(payload, "schema_version", str) != "1.0":
        raise JobValidationError("schema_version must be 1.0")
    job_id = _require_type(payload, "job_id", str)
    if not _JOB_ID_PATTERN.fullmatch(job_id):
        raise JobValidationError("job_id must match the official contract pattern")
    if _require_type(payload, "module_id", str) != "moisture":
        raise JobValidationError("module_id must be moisture")
    phase = _require_type(payload, "phase", str)
    if phase not in {"draft", "finalize"}:
        raise JobValidationError("phase must be draft or finalize")
    if _require_type(payload, "run_mode", str) not in {"single", "batch", "incremental"}:
        raise JobValidationError("run_mode is not supported by the official contract")

    input_files = _require_type(payload, "input_files", list)
    if not input_files:
        raise JobValidationError("input_files must contain at least one path")
    if not all(
        isinstance(path, str) and PureWindowsPath(path).is_absolute() for path in input_files
    ):
        raise JobValidationError("input_files must contain absolute Windows paths")
    output_dir = _require_type(payload, "output_dir", str)
    if not PureWindowsPath(output_dir).is_absolute():
        raise JobValidationError("output_dir must be an absolute Windows path")

    for field in ("module_config_file", "confirmation_file", "service_response_file"):
        _validate_optional_path(payload, field)
    if "ai_enabled" in payload and type(payload["ai_enabled"]) is not bool:
        raise JobValidationError("ai_enabled has an invalid type")
    if "allowed_knowledge_scopes" in payload:
        scopes = _require_type(payload, "allowed_knowledge_scopes", list)
        if not all(isinstance(scope, str) for scope in scopes):
            raise JobValidationError("allowed_knowledge_scopes must contain strings")
    parent_job_id = payload.get("parent_job_id")
    if parent_job_id is not None and not isinstance(parent_job_id, str):
        raise JobValidationError("parent_job_id must be a string or null")
    if phase == "finalize":
        if not parent_job_id:
            raise JobValidationError("finalize jobs require parent_job_id")
        if not payload.get("confirmation_file"):
            raise JobValidationError("finalize jobs require confirmation_file")
    return payload


def _run(job_path: Path) -> int:
    try:
        job = _load_job(job_path)
    except JobValidationError as exc:
        sys.stderr.write(f"moisture run: invalid job: {exc}\n")
        return 2

    started_at = datetime.now(UTC).isoformat()
    emit_progress(0, "Moisture bootstrap started")
    try:
        result = build_bootstrap_result(job, started_at=started_at)
        write_json_atomic(Path(job["output_dir"]) / "result.json", result)
    except Exception:
        sys.stderr.write("moisture run: unable to write result.json\n")
        return 3
    emit_progress(100, "Moisture bootstrap result written")
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "version":
        sys.stdout.write(f"{__version__}\n")
        return 0

    if parsed.command == "run":
        return _run(Path(parsed.job))

    issues = collect_runtime_issues()
    if issues:
        for issue in issues:
            sys.stderr.write(f"moisture self-check: {issue}\n")
        return 4

    sys.stderr.write("moisture self-check: ok\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

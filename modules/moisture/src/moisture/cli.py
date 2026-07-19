"""Command-line contract surface for the moisture module."""

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from moisture import __version__
from moisture.application.draft_orchestrator import run_draft
from moisture.application.finalize_orchestrator import run_finalize
from moisture.contract.job_models import JobRequest
from moisture.contract.progress import emit_progress
from moisture.contract.schema_lock import collect_schema_lock_issues
from moisture.contract.validators import (
    ContractValidationError,
    validate_job_payload,
)
from moisture.infrastructure.diagnostics import collect_runtime_issues


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


def _load_job(job_path: Path) -> JobRequest:
    if not job_path.is_absolute():
        raise JobValidationError("--job must be an absolute path")
    if not job_path.is_file():
        raise JobValidationError("job file does not exist")
    try:
        payload = json.loads(job_path.read_text(encoding="utf-8"), parse_float=Decimal)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JobValidationError("job file is not readable JSON") from exc
    return validate_job_payload(payload)


def _resolve_bootstrap_path(path: Path, field: str) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise JobValidationError(f"{field} cannot be resolved") from exc


def _validate_bootstrap_paths(job_path: Path, job: JobRequest) -> None:
    resolved_job = _resolve_bootstrap_path(job_path, "job path")
    resolved_inputs = [_resolve_bootstrap_path(path, "input path") for path in job.input_files]
    if any(path.suffix.lower() != ".xlsx" for path in resolved_inputs):
        raise JobValidationError("input_files must contain only .xlsx files")

    resolved_output_dir = _resolve_bootstrap_path(job.output_dir, "output_dir")
    result_target = _resolve_bootstrap_path(resolved_output_dir / "result.json", "result target")
    if result_target == resolved_job or result_target in resolved_inputs:
        raise JobValidationError("result target must not overwrite job or input files")
    if resolved_output_dir == resolved_job.parent:
        raise JobValidationError("output_dir must not overlap the job directory")
    if any(resolved_output_dir == path.parent for path in resolved_inputs):
        raise JobValidationError("output_dir must not overlap an input directory")


def _run(job_path: Path) -> int:
    try:
        if not job_path.is_absolute():
            raise JobValidationError("--job must be an absolute path")
        resolved_job_path = _resolve_bootstrap_path(job_path, "job path")
        job = _load_job(resolved_job_path)
        _validate_bootstrap_paths(resolved_job_path, job)
    except (ContractValidationError, JobValidationError) as exc:
        sys.stderr.write(f"moisture run: invalid job: {exc}\n")
        return 2

    emit_progress(0, "Moisture processing started")
    try:
        if job.phase.value == "draft":
            run_draft(job)
        else:
            run_finalize(job)
    except Exception:
        sys.stderr.write("moisture run: unable to write result.json\n")
        return 3
    emit_progress(100, "Moisture result written")
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "version":
        sys.stdout.write(f"{__version__}\n")
        return 0

    if parsed.command == "run":
        return _run(Path(parsed.job))

    issues = (*collect_runtime_issues(), *collect_schema_lock_issues())
    if issues:
        for issue in issues:
            sys.stderr.write(f"moisture self-check: {issue}\n")
        return 4

    sys.stdout.write("ok\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

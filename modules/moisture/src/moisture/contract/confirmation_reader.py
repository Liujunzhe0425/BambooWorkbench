"""Strict, side-effect-free reader for framework confirmation bundles."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from moisture.domain.errors import ProtocolReadError


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ConfirmationAnswer:
    confirmation_id: str
    value: object
    apply_to_batch: bool
    remember_mapping: bool


@dataclass(frozen=True, slots=True)
class ConfirmationBundle:
    schema_version: str
    job_id: str
    answers: tuple[ConfirmationAnswer, ...]


@dataclass(frozen=True, slots=True)
class ConfirmationReadResult:
    bundle: ConfirmationBundle | None
    errors: tuple[ProtocolReadError, ...] = ()


def _error(code: str, field: str, message: str) -> ProtocolReadError:
    return ProtocolReadError(code=code, field=field, message=message)


def _load_payload(path: Path | None) -> tuple[object | None, ProtocolReadError | None]:
    if path is None or not path.is_file():
        return None, _error(
            "PROTOCOL_FILE_MISSING", "$", "confirmation protocol file is missing"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeError):
        return None, _error(
            "PROTOCOL_JSON_INVALID", "$", "confirmation protocol is not valid JSON"
        )
    except OSError:
        return None, _error(
            "PROTOCOL_FILE_UNREADABLE", "$", "confirmation protocol cannot be read"
        )


def read_confirmation_bundle(
    path: Path | None,
    *,
    root_job_id: str,
    expected_confirmation_ids: Collection[str],
) -> ConfirmationReadResult:
    """Read a bundle without applying answers or deciding the task status."""

    payload, load_error = _load_payload(path)
    if load_error is not None:
        return ConfirmationReadResult(bundle=None, errors=(load_error,))
    if not isinstance(payload, Mapping):
        return ConfirmationReadResult(
            bundle=None,
            errors=(
                _error(
                    "CONFIRMATION_BUNDLE_INVALID",
                    "$",
                    "confirmation bundle must be an object",
                ),
            ),
        )

    errors: list[ProtocolReadError] = []
    allowed_fields = {"schema_version", "job_id", "answers"}
    if set(payload) != allowed_fields:
        errors.append(
            _error(
                "CONFIRMATION_BUNDLE_INVALID",
                "$",
                "confirmation bundle fields do not match the protocol",
            )
        )

    schema_version = payload.get("schema_version")
    if schema_version != "1.0":
        errors.append(
            _error(
                "CONFIRMATION_BUNDLE_INVALID",
                "schema_version",
                "confirmation schema version must be 1.0",
            )
        )
    job_id = payload.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        errors.append(
            _error(
                "CONFIRMATION_BUNDLE_INVALID", "job_id", "job identity must be a string"
            )
        )
    elif job_id != root_job_id:
        errors.append(
            _error(
                "CONFIRMATION_ROOT_JOB_MISMATCH",
                "job_id",
                "confirmation identity does not match the root job",
            )
        )

    raw_answers = payload.get("answers")
    answers: list[ConfirmationAnswer] = []
    seen_ids: set[str] = set()
    expected_ids = set(expected_confirmation_ids)
    if not isinstance(raw_answers, list):
        errors.append(
            _error(
                "CONFIRMATION_BUNDLE_INVALID", "answers", "answers must be an array"
            )
        )
    else:
        for index, raw_answer in enumerate(raw_answers):
            field = f"answers.{index}"
            if not isinstance(raw_answer, Mapping):
                errors.append(
                    _error("CONFIRMATION_ANSWER_INVALID", field, "answer must be an object")
                )
                continue
            allowed_answer_fields = {
                "confirmation_id",
                "value",
                "apply_to_batch",
                "remember_mapping",
            }
            required_answer_fields = {"confirmation_id", "value"}
            if not required_answer_fields.issubset(raw_answer) or not set(
                raw_answer
            ).issubset(allowed_answer_fields):
                errors.append(
                    _error(
                        "CONFIRMATION_ANSWER_INVALID",
                        field,
                        "answer fields do not match the protocol",
                    )
                )
                continue
            confirmation_id = raw_answer.get("confirmation_id")
            apply_to_batch = raw_answer.get("apply_to_batch", False)
            remember_mapping = raw_answer.get("remember_mapping", False)
            if not isinstance(confirmation_id, str) or not confirmation_id:
                errors.append(
                    _error(
                        "CONFIRMATION_ANSWER_INVALID",
                        f"{field}.confirmation_id",
                        "confirmation ID must be a string",
                    )
                )
                continue
            if not isinstance(apply_to_batch, bool) or not isinstance(
                remember_mapping, bool
            ):
                errors.append(
                    _error(
                        "CONFIRMATION_ANSWER_INVALID",
                        field,
                        "answer flags must be booleans",
                    )
                )
                continue
            if confirmation_id in seen_ids:
                errors.append(
                    _error(
                        "CONFIRMATION_ID_DUPLICATE",
                        f"{field}.confirmation_id",
                        "confirmation ID is duplicated",
                    )
                )
            else:
                seen_ids.add(confirmation_id)
            if confirmation_id not in expected_ids:
                errors.append(
                    _error(
                        "CONFIRMATION_ID_UNKNOWN",
                        f"{field}.confirmation_id",
                        "confirmation ID was not requested",
                    )
                )
            answers.append(
                ConfirmationAnswer(
                    confirmation_id=confirmation_id,
                    value=_freeze_json(raw_answer["value"]),
                    apply_to_batch=apply_to_batch,
                    remember_mapping=remember_mapping,
                )
            )

    for missing_id in sorted(expected_ids - seen_ids):
        errors.append(
            _error(
                "CONFIRMATION_ID_MISSING",
                f"answers.{missing_id}",
                "expected confirmation answer is missing",
            )
        )

    if errors:
        return ConfirmationReadResult(bundle=None, errors=tuple(errors))
    return ConfirmationReadResult(
        bundle=ConfirmationBundle(
            schema_version="1.0", job_id=root_job_id, answers=tuple(answers)
        )
    )

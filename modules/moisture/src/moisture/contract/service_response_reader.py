"""Strict reader for task-local shared-service response envelopes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from moisture.domain.errors import ProtocolReadError

ServiceName = Literal["knowledge", "ai"]
ProviderStatus = Literal["ok", "denied", "error", "timeout"]


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ServiceResponse:
    request_id: str
    service: ServiceName
    status: ProviderStatus
    text: str | None = None
    error: str | None = None
    items: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceResponseEnvelope:
    schema_version: str
    task_id: str
    module_id: str
    responses: tuple[ServiceResponse, ...]


@dataclass(frozen=True, slots=True)
class ServiceResponseReadResult:
    envelope: ServiceResponseEnvelope | None
    errors: tuple[ProtocolReadError, ...] = ()


def _error(code: str, field: str, message: str) -> ProtocolReadError:
    return ProtocolReadError(code=code, field=field, message=message)


def _load_payload(path: Path | None) -> tuple[object | None, ProtocolReadError | None]:
    if path is None or not path.is_file():
        return None, _error(
            "PROTOCOL_FILE_MISSING", "$", "service response protocol file is missing"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeError):
        return None, _error(
            "PROTOCOL_JSON_INVALID", "$", "service response protocol is not valid JSON"
        )
    except OSError:
        return None, _error(
            "PROTOCOL_FILE_UNREADABLE", "$", "service response protocol cannot be read"
        )


def read_service_responses(
    path: Path | None,
    *,
    root_job_id: str,
    expected_requests: Mapping[str, ServiceName],
) -> ServiceResponseReadResult:
    """Read responses while preserving provider state and making no status decision."""

    if not expected_requests:
        return ServiceResponseReadResult(envelope=None)

    payload, load_error = _load_payload(path)
    if load_error is not None:
        return ServiceResponseReadResult(envelope=None, errors=(load_error,))
    if not isinstance(payload, Mapping):
        return ServiceResponseReadResult(
            envelope=None,
            errors=(
                _error(
                    "SERVICE_ENVELOPE_INVALID",
                    "$",
                    "service response envelope must be an object",
                ),
            ),
        )

    errors: list[ProtocolReadError] = []
    allowed_fields = {"schema_version", "task_id", "module_id", "responses"}
    if set(payload) != allowed_fields:
        errors.append(
            _error(
                "SERVICE_ENVELOPE_INVALID",
                "$",
                "service envelope fields do not match the protocol",
            )
        )
    if payload.get("schema_version") != "1.0":
        errors.append(
            _error(
                "SERVICE_ENVELOPE_INVALID",
                "schema_version",
                "service schema version must be 1.0",
            )
        )
    task_id = payload.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        errors.append(
            _error(
                "SERVICE_ENVELOPE_INVALID", "task_id", "task identity must be a string"
            )
        )
    elif task_id != root_job_id:
        errors.append(
            _error(
                "SERVICE_ROOT_JOB_MISMATCH",
                "task_id",
                "service identity does not match the root job",
            )
        )
    if payload.get("module_id") != "moisture":
        errors.append(
            _error(
                "SERVICE_MODULE_MISMATCH",
                "module_id",
                "service envelope is intended for a different module",
            )
        )

    responses: list[ServiceResponse] = []
    seen_ids: set[str] = set()
    raw_responses = payload.get("responses")
    if not isinstance(raw_responses, list):
        errors.append(
            _error(
                "SERVICE_ENVELOPE_INVALID", "responses", "responses must be an array"
            )
        )
    else:
        for index, raw_response in enumerate(raw_responses):
            field = f"responses.{index}"
            response, response_errors = _parse_response(
                raw_response, field=field, expected_requests=expected_requests
            )
            errors.extend(response_errors)
            if response is None:
                continue
            if response.request_id in seen_ids:
                errors.append(
                    _error(
                        "SERVICE_RESPONSE_ID_DUPLICATE",
                        f"{field}.request_id",
                        "service response ID is duplicated",
                    )
                )
            else:
                seen_ids.add(response.request_id)
            responses.append(response)

    if errors:
        return ServiceResponseReadResult(envelope=None, errors=tuple(errors))
    return ServiceResponseReadResult(
        envelope=ServiceResponseEnvelope(
            schema_version="1.0",
            task_id=root_job_id,
            module_id="moisture",
            responses=tuple(responses),
        )
    )


def _parse_response(
    payload: object,
    *,
    field: str,
    expected_requests: Mapping[str, ServiceName],
) -> tuple[ServiceResponse | None, tuple[ProtocolReadError, ...]]:
    if not isinstance(payload, Mapping):
        return None, (
            _error("SERVICE_RESPONSE_INVALID", field, "service response must be an object"),
        )
    allowed_fields = {"request_id", "service", "status", "text", "error", "items"}
    if not {"request_id", "service", "status"}.issubset(payload) or not set(
        payload
    ).issubset(allowed_fields):
        return None, (
            _error(
                "SERVICE_RESPONSE_INVALID",
                field,
                "service response fields do not match the protocol",
            ),
        )

    errors: list[ProtocolReadError] = []
    request_id = payload.get("request_id")
    service = payload.get("service")
    status = payload.get("status")
    if not isinstance(request_id, str) or not request_id:
        errors.append(
            _error(
                "SERVICE_RESPONSE_INVALID",
                f"{field}.request_id",
                "request ID must be a string",
            )
        )
    elif request_id not in expected_requests:
        errors.append(
            _error(
                "SERVICE_RESPONSE_ID_UNKNOWN",
                f"{field}.request_id",
                "service response ID was not requested",
            )
        )
    if service not in {"knowledge", "ai"}:
        errors.append(
            _error(
                "SERVICE_RESPONSE_INVALID",
                f"{field}.service",
                "service name is invalid",
            )
        )
    elif (
        isinstance(request_id, str)
        and request_id in expected_requests
        and expected_requests[request_id] != service
    ):
        errors.append(
            _error(
                "SERVICE_RESPONSE_SERVICE_MISMATCH",
                f"{field}.service",
                "service response does not match its request",
            )
        )
    if status not in {"ok", "denied", "error", "timeout"}:
        errors.append(
            _error(
                "SERVICE_RESPONSE_INVALID",
                f"{field}.status",
                "provider status is invalid",
            )
        )

    text = payload.get("text")
    error_text = payload.get("error")
    raw_items = payload.get("items", [])
    if text is not None and not isinstance(text, str):
        errors.append(
            _error(
                "SERVICE_RESPONSE_INVALID", f"{field}.text", "response text is invalid"
            )
        )
    if error_text is not None and not isinstance(error_text, str):
        errors.append(
            _error(
                "SERVICE_RESPONSE_INVALID", f"{field}.error", "response error is invalid"
            )
        )
    if not isinstance(raw_items, list) or any(
        not isinstance(item, Mapping) for item in raw_items
    ):
        errors.append(
            _error(
                "SERVICE_RESPONSE_INVALID", f"{field}.items", "response items are invalid"
            )
        )
    if errors:
        return None, tuple(errors)

    frozen_items = tuple(_freeze_json(item) for item in raw_items)
    return (
        ServiceResponse(
            request_id=request_id,
            service=service,
            status=status,
            text=text,
            error=error_text,
            items=frozen_items,
        ),
        (),
    )

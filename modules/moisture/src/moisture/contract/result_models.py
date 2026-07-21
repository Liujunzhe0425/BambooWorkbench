"""Immutable boundary models for the official ModuleResult contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from moisture.contract.job_models import ModuleId


class TaskStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NEEDS_CONFIRMATION = "needs_confirmation"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ServiceType(StrEnum):
    KNOWLEDGE = "knowledge"
    AI = "ai"


class ResultModelError(ValueError):
    def __init__(self, code: str, field: str, message: str) -> None:
        self.code = code
        self.field = field
        super().__init__(message)


def _freeze_json(value: Any, field: str) -> Any:
    if value is None or isinstance(value, (str, bool, int, float, Decimal)):
        return value
    if isinstance(value, list):
        return tuple(
            _freeze_json(item, f"{field}.{index}") for index, item in enumerate(value)
        )
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ResultModelError(
                "CONTRACT_SEMANTIC_INVALID", field, "JSON object keys must be strings"
            )
        return MappingProxyType(
            {key: _freeze_json(item, f"{field}.{key}") for key, item in value.items()}
        )
    raise ResultModelError(
        "CONTRACT_SEMANTIC_INVALID", field, "value is not JSON-compatible"
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _decimal(value: int | float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class ResultSummary:
    input_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    anomaly_count: int
    confirmation_count: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ResultSummary:
        return cls(**payload)

    def to_payload(self) -> dict[str, int]:
        return {
            "input_count": self.input_count,
            "processed_count": self.processed_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "anomaly_count": self.anomaly_count,
            "confirmation_count": self.confirmation_count,
        }

@dataclass(frozen=True, slots=True)
class SourceRef:
    source_file: Path
    sheet: str | None = None
    cell_or_range: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SourceRef:
        return cls(
            source_file=Path(payload["source_file"]),
            sheet=payload.get("sheet"),
            cell_or_range=payload.get("cell_or_range"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_file": str(self.source_file),
            "sheet": self.sheet,
            "cell_or_range": self.cell_or_range,
        }


@dataclass(frozen=True, slots=True)
class Anomaly:
    anomaly_id: str
    severity: Severity
    field: str
    message: str
    source: SourceRef
    value: Any = None
    rule_id: str | None = None
    suggestion: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Anomaly:
        return cls(
            anomaly_id=payload["anomaly_id"],
            severity=Severity(payload["severity"]),
            field=payload["field"],
            value=_freeze_json(payload.get("value"), "anomalies.value"),
            rule_id=payload.get("rule_id"),
            message=payload["message"],
            suggestion=payload.get("suggestion"),
            source=SourceRef.from_payload(payload["source"]),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "severity": self.severity.value,
            "field": self.field,
            "value": _json_value(self.value),
            "rule_id": self.rule_id,
            "message": self.message,
            "suggestion": self.suggestion,
            "source": self.source.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class ConfirmationPrompt:
    confirmation_id: str
    field: str
    reason: str
    confidence: Decimal
    blocking: bool
    batch_applicable: bool
    rememberable: bool
    source: SourceRef
    suggested_value: Any = None
    options: tuple[Any, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ConfirmationPrompt:
        return cls(
            confirmation_id=payload["confirmation_id"],
            field=payload["field"],
            reason=payload["reason"],
            suggested_value=_freeze_json(
                payload.get("suggested_value"), "confirmations.suggested_value"
            ),
            options=tuple(
                _freeze_json(value, "confirmations.options")
                for value in payload.get("options", [])
            ),
            confidence=_decimal(payload["confidence"]),
            blocking=payload["blocking"],
            batch_applicable=payload["batch_applicable"],
            rememberable=payload["rememberable"],
            source=SourceRef.from_payload(payload["source"]),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "field": self.field,
            "reason": self.reason,
            "suggested_value": _json_value(self.suggested_value),
            "options": _json_value(self.options),
            "confidence": float(self.confidence),
            "blocking": self.blocking,
            "batch_applicable": self.batch_applicable,
            "rememberable": self.rememberable,
            "source": self.source.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class OutputArtifact:
    type: str
    path: Path
    label: str
    mime_type: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> OutputArtifact:
        return cls(
            type=payload["type"],
            path=Path(payload["path"]),
            label=payload["label"],
            mime_type=payload["mime_type"],
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "type": self.type,
            "path": str(self.path),
            "label": self.label,
            "mime_type": self.mime_type,
        }


@dataclass(frozen=True, slots=True)
class FileResult:
    source_file: Path
    fingerprint: str
    status: TaskStatus
    extracted_records: int
    anomaly_count: int
    missing_fields: tuple[str, ...] = ()
    error: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> FileResult:
        return cls(
            source_file=Path(payload["source_file"]),
            fingerprint=payload["fingerprint"],
            status=TaskStatus(payload["status"]),
            extracted_records=payload["extracted_records"],
            missing_fields=tuple(payload.get("missing_fields", [])),
            anomaly_count=payload["anomaly_count"],
            error=payload.get("error"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_file": str(self.source_file),
            "fingerprint": self.fingerprint,
            "status": self.status.value,
            "extracted_records": self.extracted_records,
            "missing_fields": list(self.missing_fields),
            "anomaly_count": self.anomaly_count,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ServiceRequest:
    request_id: str
    service: ServiceType
    purpose: str
    payload: Mapping[str, Any]
    scope: str | None = None
    requires_user_consent: bool = True

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ServiceRequest:
        frozen_payload = _freeze_json(payload["payload"], "service_requests.payload")
        if not isinstance(frozen_payload, Mapping):
            raise ResultModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "service_requests.payload",
                "service payload must be an object",
            )
        return cls(
            request_id=payload["request_id"],
            service=ServiceType(payload["service"]),
            scope=payload.get("scope"),
            purpose=payload["purpose"],
            payload=frozen_payload,
            requires_user_consent=payload.get("requires_user_consent", True),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "service": self.service.value,
            "scope": self.scope,
            "purpose": self.purpose,
            "payload": _json_value(self.payload),
            "requires_user_consent": self.requires_user_consent,
        }


@dataclass(frozen=True, slots=True)
class ModuleResult:
    schema_version: str
    job_id: str
    module_id: ModuleId
    module_version: str
    status: TaskStatus
    summary: ResultSummary
    started_at: datetime
    finished_at: datetime
    rule_version: str | None = None
    anomalies: tuple[Anomaly, ...] = ()
    confirmations: tuple[ConfirmationPrompt, ...] = ()
    outputs: tuple[OutputArtifact, ...] = ()
    file_results: tuple[FileResult, ...] = ()
    service_requests: tuple[ServiceRequest, ...] = ()
    analysis_summary: str | None = None
    errors: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ModuleResult:
        module_id = ModuleId(payload["module_id"])
        if module_id is not ModuleId.MOISTURE:
            raise ResultModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "module_id",
                "result is intended for a different module",
            )
        confirmations = tuple(
            ConfirmationPrompt.from_payload(item)
            for item in payload.get("confirmations", [])
        )
        summary = ResultSummary.from_payload(payload["summary"])
        status = TaskStatus(payload["status"])
        if status is TaskStatus.NEEDS_CONFIRMATION and not confirmations:
            raise ResultModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "confirmations",
                "needs_confirmation requires at least one prompt",
            )
        if summary.confirmation_count != len(confirmations):
            raise ResultModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "summary.confirmation_count",
                "confirmation count does not match prompt list",
            )

        return cls(
            schema_version=payload["schema_version"],
            job_id=payload["job_id"],
            module_id=module_id,
            module_version=payload["module_version"],
            status=status,
            rule_version=payload.get("rule_version"),
            summary=summary,
            anomalies=tuple(
                Anomaly.from_payload(item) for item in payload.get("anomalies", [])
            ),
            confirmations=confirmations,
            outputs=tuple(
                OutputArtifact.from_payload(item)
                for item in payload.get("outputs", [])
            ),
            file_results=tuple(
                FileResult.from_payload(item)
                for item in payload.get("file_results", [])
            ),
            service_requests=tuple(
                ServiceRequest.from_payload(item)
                for item in payload.get("service_requests", [])
            ),
            analysis_summary=payload.get("analysis_summary"),
            errors=tuple(payload.get("errors", [])),
            started_at=datetime.fromisoformat(payload["started_at"]),
            finished_at=datetime.fromisoformat(payload["finished_at"]),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "module_id": self.module_id.value,
            "module_version": self.module_version,
            "status": self.status.value,
            "rule_version": self.rule_version,
            "summary": self.summary.to_payload(),
            "anomalies": [item.to_payload() for item in self.anomalies],
            "confirmations": [item.to_payload() for item in self.confirmations],
            "outputs": [item.to_payload() for item in self.outputs],
            "file_results": [item.to_payload() for item in self.file_results],
            "service_requests": [item.to_payload() for item in self.service_requests],
            "analysis_summary": self.analysis_summary,
            "errors": list(self.errors),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }

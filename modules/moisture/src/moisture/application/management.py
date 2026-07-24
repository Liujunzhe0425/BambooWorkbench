"""Narrow, offline history and approved-experience management operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from moisture.adapters.experience.data_root import (
    initialize_managed_root,
    needs_initialization,
)
from moisture.adapters.experience.local_approved_repository import (
    LocalApprovedExperienceRepository,
)
from moisture.adapters.history.repository import HistoryRepository
from moisture.contract.management import (
    ManagementContractError,
    validate_management_response,
)
from moisture.infrastructure.atomic_write import write_json_atomic


class ManagementOperationError(RuntimeError):
    """A safe public management operation failure."""


def _data_dir(request: dict[str, Any]) -> Path:
    candidate = Path(request["data_dir"])
    if not candidate.is_absolute():
        raise ManagementOperationError("模块数据目录无效")
    expected = os.environ.get("BAMBOO_MOISTURE_DATA_DIR")
    if expected is not None:
        try:
            if candidate.resolve(strict=False) != Path(expected).resolve(strict=False):
                raise ManagementOperationError("模块数据目录与框架授权不一致")
        except OSError as error:
            raise ManagementOperationError("模块数据目录无法解析") from error
    return candidate


def _history_items(repository: HistoryRepository) -> list[dict[str, object]]:
    return [
        {
            "history_id": entry["history_id"],
            "display_name": entry["display_name"][:160],
            "sha256": entry["sha256"],
            "date_start": entry["date_start"],
            "date_end": entry["date_end"],
            "active": entry["status"] == "active",
        }
        for entry in repository.list_entries()
    ]


def _experience_items(data_dir: Path) -> list[dict[str, object]]:
    experience_root = data_dir / "experience"
    if needs_initialization(experience_root):
        initialize_managed_root(experience_root)
    references = LocalApprovedExperienceRepository(experience_root).list_approved()
    return [
        {
            "entry_id": reference.experience_id,
            "title": reference.title,
            "version": reference.version,
            "sha256": reference.content_hash,
            "valid_from": reference.effective_at.date().isoformat(),
            "valid_until": None,
        }
        for reference in references
    ]


def execute_management(request: dict[str, Any]) -> dict[str, Any]:
    """Execute one framework-authorized management operation."""

    operation = request["operation"]
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "module_id": "moisture",
        "operation": operation,
        "status": "ok",
    }
    data_dir = _data_dir(request)
    repository = HistoryRepository(data_dir / "history")
    if operation == "list_history_summaries":
        base["history_items"] = _history_items(repository)
    elif operation == "import_history_summary":
        input_file = Path(request["input_file"])
        display_name = input_file.name[:160]
        base["imported_history_id"] = repository.import_summary(input_file, display_name)
    elif operation == "retire_history_summary":
        repository.retire_entry(request["history_id"])
    elif operation == "list_approved_experiences":
        base["experience_items"] = _experience_items(data_dir)
    else:
        raise ManagementOperationError("不支持的资料管理操作")
    return validate_management_response(base)


def error_response(request: dict[str, Any], error_code: str, message: str) -> dict[str, Any]:
    """Build a path-free, schema-valid public error response."""

    payload = {
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "module_id": "moisture",
        "operation": request["operation"],
        "status": "error",
        "error_code": error_code[:80],
        "message": message.replace("\r", " ").replace("\n", " ")[:300],
    }
    return validate_management_response(payload)


def publish_management_response(path: Path, payload: dict[str, Any]) -> None:
    """Publish the validated response atomically."""

    if not path.is_absolute():
        raise ManagementContractError("响应路径必须是绝对路径")
    validate_management_response(payload)
    write_json_atomic(path, payload)

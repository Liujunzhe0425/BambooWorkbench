"""Process-isolated public history, experience, and rule management."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from moisture.adapters.experience.data_root import (
    initialize_managed_root,
    needs_initialization,
)
from moisture.adapters.experience.local_approved_repository import (
    ExperienceRepositoryError,
    LocalApprovedExperienceRepository,
)
from moisture.adapters.experience.local_editable_repository import (
    ExperienceAdminConflictError,
    ExperienceAdminError,
    ExperienceAdminSecurityError,
    ExperienceAdminValidationError,
    LocalEditableExperienceRepository,
)
from moisture.adapters.history.repository import (
    HistoryImportError,
    HistoryIntegrityError,
    HistoryRepository,
    HistoryRepositoryError,
    HistorySecurityError,
)
from moisture.adapters.rules.data_root import ManagedRuleError
from moisture.adapters.rules.local_editable_repository import (
    LocalEditableRuleRepository,
    RuleAdminConflictError,
    RuleAdminError,
    RuleAdminPackage,
    RuleAdminSummary,
    RuleAdminValidationError,
    RulePreview,
)
from moisture.application.experience_management import ExperienceManagementService
from moisture.application.rule_management import RuleManagementService
from moisture.contract.management import (
    ManagementContractError,
    validate_management_response,
)
from moisture.infrastructure.atomic_write import write_json_atomic
from moisture.ports.experience_admin_repository import (
    AdminExperience,
    AdminExperienceSummary,
)

_EXPERIENCE_MUTATIONS = {
    "create_experience_draft",
    "update_experience_draft",
    "publish_experience",
    "retire_experience",
    "copy_experience_history_to_draft",
}
_RULE_MUTATIONS = {
    "create_rule_draft",
    "update_rule_draft",
    "publish_rule",
    "retire_current_rule",
    "restore_rule_version",
    "copy_rule_history_to_draft",
}


class ManagementOperationError(RuntimeError):
    """A stable, path-free public management operation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def _is_reparse_point(path: Path) -> bool:
    try:
        linked = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(
        getattr(linked, "st_file_attributes", 0) & reparse_flag
    )


def _data_dir(request: dict[str, Any]) -> Path:
    candidate = Path(request["data_dir"])
    if not candidate.is_absolute() or (candidate.exists() and _is_reparse_point(candidate)):
        raise ManagementOperationError(
            "MANAGEMENT_PATH_REJECTED", "模块数据目录未获授权"
        )
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as error:
        raise ManagementOperationError(
            "MANAGEMENT_PATH_REJECTED", "模块数据目录无法安全解析"
        ) from error
    expected = os.environ.get("BAMBOO_MOISTURE_DATA_DIR")
    if expected is not None:
        try:
            authorized = Path(expected).resolve(strict=False)
        except OSError as error:
            raise ManagementOperationError(
                "MANAGEMENT_PATH_REJECTED", "框架授权目录无法安全解析"
            ) from error
        if resolved != authorized:
            raise ManagementOperationError(
                "MANAGEMENT_PATH_REJECTED", "模块数据目录与框架授权不一致"
            )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _history_item(entry: dict[str, object]) -> dict[str, object]:
    return {
        "history_id": entry["history_id"],
        "display_name": str(entry["display_name"])[:160],
        "sha256": entry["sha256"],
        "date_start": entry["date_start"],
        "date_end": entry["date_end"],
        "active": entry["status"] == "active",
    }


def _history_items(repository: HistoryRepository) -> list[dict[str, object]]:
    return [_history_item(entry) for entry in repository.list_entries()]


def _approved_experience_items(data_dir: Path) -> list[dict[str, object]]:
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


def _scope_values(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or ["*"]


def _experience_summary(item: AdminExperienceSummary) -> dict[str, object]:
    return {
        "experience_id": item.experience_id,
        "version": item.version,
        "status": item.status,
        "title": item.title,
        "source": item.source,
        "sha256": item.sha256,
        "effective_at": item.effective_at,
        "applicable_suppliers": _scope_values(item.applicable_suppliers),
        "applicable_materials": _scope_values(item.applicable_materials),
        "applicable_seasons": _scope_values(item.applicable_seasons),
        "applicable_metrics": _scope_values(item.applicable_metrics),
        "supersedes": item.supersedes or None,
    }


def _experience(item: AdminExperience) -> dict[str, object]:
    return {
        "experience_id": item.experience_id,
        "version": item.version,
        "status": item.status,
        "sha256": item.sha256,
        "document": item.document,
    }


def _rule(item: RuleAdminSummary) -> dict[str, object]:
    return {
        "rule_version": item.rule_version,
        "package_id": item.package_id,
        "lifecycle": item.lifecycle,
        "rules_sha256": item.rules_sha256,
        "package_hash": item.package_hash,
        "source": item.source,
        "applicable_scope": item.applicable_scope,
        "confirmation_status": item.confirmation_status,
    }


def _rule_package(item: RuleAdminPackage) -> dict[str, object]:
    return {
        **_rule(item.summary),
        "manifest": item.manifest,
        "rules_yaml": item.rules_yaml,
    }


def _rule_preview(item: RulePreview) -> dict[str, object]:
    return {
        "batch_count": item.batch_count,
        "matched_batch_count": item.matched_batch_count,
        "decision_count": item.decision_count,
        "pending_match_count": item.pending_match_count,
        "warnings": list(item.warnings),
    }


def _experience_service(data_dir: Path) -> ExperienceManagementService:
    root = data_dir / "experience"
    if needs_initialization(root):
        initialize_managed_root(root)
    return ExperienceManagementService(LocalEditableExperienceRepository(root))


def _rule_service(data_dir: Path) -> RuleManagementService:
    return RuleManagementService(LocalEditableRuleRepository(data_dir / "rules"))


def _legacy_success(request: dict[str, Any]) -> dict[str, Any]:
    operation = request["operation"]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "module_id": "moisture",
        "operation": operation,
        "status": "ok",
    }
    data_dir = _data_dir(request)
    repository = HistoryRepository(data_dir / "history")
    if operation == "list_history_summaries":
        payload["history_items"] = _history_items(repository)
    elif operation == "import_history_summary":
        input_file = Path(request["input_file"])
        payload["imported_history_id"] = repository.import_summary(
            input_file, input_file.name[:160]
        )
    elif operation == "retire_history_summary":
        repository.retire_entry(request["history_id"])
    elif operation == "list_approved_experiences":
        payload["experience_items"] = _approved_experience_items(data_dir)
    else:
        raise ManagementOperationError(
            "MANAGEMENT_OPERATION_UNSUPPORTED", "不支持的管理操作"
        )
    return validate_management_response(payload)


def _unified_success(request: dict[str, Any]) -> dict[str, Any]:
    operation = request["operation"]
    parameters = request["parameters"]
    data_dir = _data_dir(request)
    result: dict[str, object]

    if operation in {
        "list_approved_experiences",
        "import_history_summary",
        "list_history_summaries",
        "retire_history_summary",
        "preview_rule_draft",
    }:
        history_repository = HistoryRepository(data_dir / "history")
    else:
        history_repository = None

    if operation == "list_approved_experiences":
        result = {"experience_items": _approved_experience_items(data_dir)}
    elif operation == "import_history_summary":
        input_file = Path(parameters["input_file"])
        history_id = history_repository.import_summary(
            input_file, input_file.name[:160]
        )
        result = {"imported_history_id": history_id}
    elif operation == "list_history_summaries":
        result = {"history_items": _history_items(history_repository)}
    elif operation == "retire_history_summary":
        history_repository.retire_entry(parameters["history_id"])
        item = history_repository.get_entry(parameters["history_id"])
        if item is None:
            raise KeyError(parameters["history_id"])
        result = {"history_item": _history_item(item)}
    elif operation.startswith(("list_experience_", "show_experience")) or operation in {
        "validate_experience_draft",
        "create_experience_draft",
        "update_experience_draft",
        "publish_experience",
        "retire_experience",
        "copy_experience_history_to_draft",
    }:
        service = _experience_service(data_dir)
        if operation == "list_experience_drafts":
            result = {
                "experience_items": [
                    _experience_summary(item) for item in service.list_drafts()
                ]
            }
        elif operation == "list_experience_approved":
            result = {
                "experience_items": [
                    _experience_summary(item) for item in service.list_approved()
                ]
            }
        elif operation == "list_experience_history":
            result = {
                "experience_items": [
                    _experience_summary(item) for item in service.list_history()
                ]
            }
        elif operation == "show_experience":
            item = service.show(parameters["experience_id"], parameters["version"])
            result = {"experience": _experience(item)}
        elif operation == "validate_experience_draft":
            result = {"experience": _experience(service.validate(parameters["document"]))}
        elif operation == "create_experience_draft":
            result = {"experience": _experience(service.create(parameters["document"]))}
        elif operation == "update_experience_draft":
            item = service.update(
                parameters["experience_id"],
                parameters["version"],
                parameters["document"],
                parameters["expected_hash"],
            )
            result = {"experience": _experience(item)}
        elif operation == "publish_experience":
            item = service.publish(
                parameters["experience_id"],
                parameters["version"],
                parameters["expected_hash"],
            )
            result = {"experience": _experience(item)}
        elif operation == "retire_experience":
            item = service.retire(
                parameters["experience_id"],
                parameters["version"],
                parameters["expected_hash"],
            )
            result = {"experience": _experience(item)}
        else:
            item = service.copy_retired_to_draft(
                parameters["experience_id"],
                parameters["version"],
                parameters["expected_hash"],
                parameters["new_version"],
            )
            result = {"experience": _experience(item)}
    else:
        service = _rule_service(data_dir)
        if operation == "get_active_rule_identity":
            current = service.list_current()
            if not current:
                raise ManagementOperationError(
                    "RULE_ACTIVE_NOT_FOUND", "当前没有有效规则"
                )
            result = {
                "active_rule": {
                    "version": current[0].rule_version,
                    "sha256": current[0].rules_sha256,
                }
            }
        elif operation == "list_rule_drafts":
            result = {"rule_items": [_rule(item) for item in service.list_drafts()]}
        elif operation == "list_current_rules":
            result = {"rule_items": [_rule(item) for item in service.list_current()]}
        elif operation == "list_rule_history":
            result = {"rule_items": [_rule(item) for item in service.list_history()]}
        elif operation == "show_rule_package":
            result = {
                "rule_package": _rule_package(
                    service.show_package(parameters["rule_version"])
                )
            }
        elif operation == "validate_rule_draft":
            result = {
                "rule": _rule(service.validate_draft(parameters["rule_version"]))
            }
        elif operation == "preview_rule_draft":
            summaries = tuple(
                history_repository.resolve_active_summary(history_id)
                for history_id in parameters["history_ids"]
            )
            result = {
                "rule_preview": _rule_preview(
                    service.preview_draft(parameters["rule_version"], summaries)
                )
            }
        elif operation == "create_rule_draft":
            result = {
                "rule": _rule(
                    service.create_draft(
                        parameters["manifest"], parameters["rules_yaml"]
                    )
                )
            }
        elif operation == "update_rule_draft":
            result = {
                "rule": _rule(
                    service.update_draft(
                        parameters["rule_version"],
                        parameters["manifest"],
                        parameters["rules_yaml"],
                        parameters["expected_package_hash"],
                    )
                )
            }
        elif operation == "publish_rule":
            result = {
                "rule": _rule(
                    service.publish(
                        parameters["rule_version"],
                        parameters["expected_package_hash"],
                    )
                )
            }
        elif operation == "retire_current_rule":
            result = {
                "rule": _rule(
                    service.retire_current(parameters["expected_rules_sha256"])
                )
            }
        elif operation == "restore_rule_version":
            result = {
                "rule": _rule(
                    service.restore(
                        parameters["rule_version"],
                        parameters["expected_rules_sha256"],
                    )
                )
            }
        elif operation == "copy_rule_history_to_draft":
            result = {
                "rule": _rule(
                    service.copy_history_to_draft(
                        parameters["rule_version"],
                        parameters["expected_package_hash"],
                        parameters["new_version"],
                    )
                )
            }
        else:
            raise ManagementOperationError(
                "MANAGEMENT_OPERATION_UNSUPPORTED", "不支持的管理操作"
            )

    return validate_management_response(
        {
            "schema_version": "1.1",
            "request_id": request["request_id"],
            "module_id": "moisture",
            "operation": operation,
            "status": "ok",
            "result": result,
        }
    )


def execute_management(request: dict[str, Any]) -> dict[str, Any]:
    """Execute one already validated framework-authorized operation."""

    if request["schema_version"] == "1.0":
        return _legacy_success(request)
    return _unified_success(request)


def _conflict_code(prefix: str, operation: str, message: str) -> str:
    lowered = message.casefold()
    if "hash" in lowered:
        return f"{prefix}_HASH_CONFLICT"
    if operation.startswith(("create_", "copy_")) or "version already" in lowered:
        return f"{prefix}_VERSION_CONFLICT"
    return f"{prefix}_STATE_CONFLICT"


def public_management_error(
    request: dict[str, Any], error: Exception
) -> ManagementOperationError | None:
    """Map known internal failures to a stable, redacted public error."""

    if isinstance(error, ManagementOperationError):
        return error
    operation = str(request.get("operation", ""))
    if isinstance(error, ManagementContractError):
        return ManagementOperationError(
            "MANAGEMENT_REQUEST_INVALID", "管理请求不符合公开合同"
        )
    if isinstance(error, ExperienceAdminSecurityError):
        return ManagementOperationError(
            "EXPERIENCE_PATH_REJECTED", "经验路径或标识不安全"
        )
    if isinstance(error, ExperienceAdminConflictError):
        return ManagementOperationError(
            _conflict_code("EXPERIENCE", operation, str(error)),
            "经验已变化或当前状态不允许该操作",
        )
    if isinstance(error, ExperienceAdminValidationError):
        return ManagementOperationError(
            "EXPERIENCE_SCHEMA_INVALID", "经验内容不符合 Schema"
        )
    if isinstance(error, ExperienceRepositoryError):
        return ManagementOperationError(
            "MANAGEMENT_DATA_CORRUPTED", "经验目录损坏或不完整"
        )
    if isinstance(error, RuleAdminConflictError):
        return ManagementOperationError(
            _conflict_code("RULE", operation, str(error)),
            "规则已变化或当前状态不允许该操作",
        )
    if isinstance(error, RuleAdminValidationError):
        code = (
            "RULE_PATH_REJECTED"
            if "unsafe" in str(error).casefold()
            else "RULE_SCHEMA_INVALID"
        )
        return ManagementOperationError(code, "规则包不符合约束")
    if isinstance(error, ManagedRuleError):
        return ManagementOperationError(
            "MANAGEMENT_DATA_CORRUPTED", "规则目录损坏或不完整"
        )
    if isinstance(error, HistorySecurityError):
        return ManagementOperationError(
            "MANAGEMENT_PATH_REJECTED", "历史资料路径未获授权"
        )
    if isinstance(error, HistoryIntegrityError):
        return ManagementOperationError(
            "MANAGEMENT_DATA_CORRUPTED", "历史资料目录损坏或不完整"
        )
    if isinstance(error, HistoryImportError):
        return ManagementOperationError(
            "MANAGEMENT_OPERATION_FAILED", "历史汇总文件不可用"
        )
    if isinstance(error, KeyError):
        if "experience" in operation:
            return ManagementOperationError(
                "EXPERIENCE_NOT_FOUND", "指定经验不存在"
            )
        if "rule" in operation:
            return ManagementOperationError("RULE_NOT_FOUND", "指定规则不存在")
        return ManagementOperationError(
            "MANAGEMENT_OPERATION_FAILED", "指定历史资料不存在"
        )
    if isinstance(error, OSError):
        if operation in _EXPERIENCE_MUTATIONS:
            return ManagementOperationError(
                "EXPERIENCE_WRITE_FAILED", "经验写入失败，原版本保持不变"
            )
        if operation in _RULE_MUTATIONS:
            return ManagementOperationError(
                "RULE_WRITE_FAILED", "规则写入失败，原版本保持不变"
            )
        return ManagementOperationError(
            "MANAGEMENT_OPERATION_FAILED", "资料操作失败"
        )
    if isinstance(error, (ExperienceAdminError, RuleAdminError, HistoryRepositoryError)):
        return ManagementOperationError(
            "MANAGEMENT_OPERATION_FAILED", "资料操作失败"
        )
    if isinstance(error, ValueError):
        return ManagementOperationError(
            "MANAGEMENT_DATA_CORRUPTED", "管理数据损坏或不完整"
        )
    return None


def error_response(
    request: dict[str, Any], error_code: str, message: str
) -> dict[str, Any]:
    """Build a path-free, schema-valid response for an expected failure."""

    payload = {
        "schema_version": request["schema_version"],
        "request_id": request["request_id"],
        "module_id": "moisture",
        "operation": request["operation"],
        "status": "error",
        "error_code": error_code[:80],
        "message": message.replace("\r", " ").replace("\n", " ")[:300],
    }
    return validate_management_response(payload)


def publish_management_response(path: Path, payload: dict[str, Any]) -> None:
    """Validate and atomically publish a management response."""

    if not path.is_absolute() or path.is_symlink():
        raise ManagementContractError("响应路径必须是安全的绝对路径")
    validate_management_response(payload)
    write_json_atomic(path, payload)

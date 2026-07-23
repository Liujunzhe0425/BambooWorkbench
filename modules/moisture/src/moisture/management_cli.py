"""Process-isolated management command used by BambooWorkbench."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from moisture.adapters.experience.local_approved_repository import (
    ExperienceRepositoryError,
)
from moisture.adapters.history.repository import HistoryRepositoryError
from moisture.application.management import (
    ManagementOperationError,
    error_response,
    execute_management,
    publish_management_response,
)
from moisture.contract.management import (
    ManagementContractError,
    validate_management_request,
)
from moisture.contract.progress import emit_progress


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ManagementContractError("管理请求包含重复字段")
        payload[key] = value
    return payload


def _load_request(path: Path) -> dict[str, object]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ManagementContractError("管理请求文件无效")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManagementContractError("管理请求不是有效 JSON") from error
    return validate_management_request(payload)


def run_management(request_path: Path, response_path: Path) -> int:
    """Run one request and always isolate expected business failures."""

    try:
        request = _load_request(request_path)
    except ManagementContractError as error:
        sys.stderr.write(f"moisture manage: {error}\n")
        return 2
    if not response_path.is_absolute() or response_path == request_path:
        sys.stderr.write("moisture manage: 响应路径无效\n")
        return 2

    emit_progress(0, "水分资料管理开始")
    try:
        response = execute_management(request)
    except (
        ExperienceRepositoryError,
        HistoryRepositoryError,
        ManagementContractError,
        ManagementOperationError,
        KeyError,
        OSError,
        ValueError,
    ):
        response = error_response(
            request, "MANAGEMENT_OPERATION_FAILED", "资料操作失败，请检查输入"
        )
    try:
        publish_management_response(response_path, response)
    except (ManagementContractError, OSError):
        sys.stderr.write("moisture manage: 无法写入管理响应\n")
        return 3
    emit_progress(100, "水分资料管理完成")
    return 0

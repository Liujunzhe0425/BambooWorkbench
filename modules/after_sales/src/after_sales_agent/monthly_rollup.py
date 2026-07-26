from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from after_sales_agent import MODULE_ID, MODULE_VERSION
from after_sales_agent.report import write_summary_workbook
from after_sales_agent.visual_reports import (
    write_annual_monthly_fee_workbook,
    write_brand_share_workbook,
    write_issue_share_workbook,
    write_yearly_chart_dashboard_workbook,
)
from after_sales_agent.word_report import write_word_analysis_report

SNAPSHOT_SCHEMA_VERSION = "1.0"
SNAPSHOT_FORMAT = "module-owned-v1"
ROLLUP_SCHEMA_VERSION = "1.0"
ISSUE_TYPES = {"性能", "外观", "加工", "其他"}

_SNAPSHOT_RECORD_FIELDS = (
    "input_index",
    "file_sha256",
    "analysis_status",
    "included_in_summary",
    "product",
    "spec",
    "order_no",
    "complaint_date",
    "year",
    "month",
    "brand",
    "issue_types",
    "primary_issue_type",
    "after_sales_fee_amount",
    "after_sales_fee_status",
    "after_sales_fee_reviewed",
    "fee_amount",
    "fee_status",
    "enterprise_cost_amount",
    "enterprise_cost_status",
    "enterprise_cost_reviewed",
    "internal_accountability_amount",
    "internal_accountability_status",
    "internal_accountability_reviewed",
    "external_borne_amount",
    "external_borne_status",
    "external_borne_reviewed",
    "fee_currency",
    "responsible_factory",
    "responsibility_reviewed",
    "complaint_type_reviewed",
    "manual_review_completed",
    "resolution_status",
    "case_status",
    "closed",
    "reviewed",
)


class MonthlyRollupError(ValueError):
    """Stable module-owned error for snapshot and cumulative rendering."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def write_finalize_monthly_snapshot(
    records: list[dict[str, Any]],
    output_dir: Path,
    *,
    year: int,
    month: int,
) -> Path | None:
    """Write the one target-period snapshot declared by the central job contract."""

    period_records = [
        record
        for record in records
        if record.get("included_in_summary", True)
        and _integer(record.get("year")) == year
        and _integer(record.get("month")) == month
    ]
    if not period_records or any(
        not _record_is_final(record) for record in period_records
    ):
        return None

    snapshot = build_monthly_snapshot(period_records, year=year, month=month)
    path = output_dir / "after_sales_monthly_snapshot.json"
    _atomic_write_json(path, snapshot)
    return path


def build_monthly_snapshot(
    records: list[dict[str, Any]],
    *,
    year: int,
    month: int,
) -> dict[str, Any]:
    if year < 2000 or year > 9999:
        raise MonthlyRollupError("SNAPSHOT_YEAR_INVALID", "月度快照年份不合法。")
    if month < 1 or month > 12:
        raise MonthlyRollupError("SNAPSHOT_MONTH_INVALID", "月度快照月份不合法。")
    if not records:
        raise MonthlyRollupError("SNAPSHOT_RECORDS_EMPTY", "月度快照没有正式业务记录。")

    sanitized: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        if not _record_is_final(record):
            raise MonthlyRollupError(
                "SNAPSHOT_RECORD_NOT_FINAL",
                "月度快照只能包含已完成人工确认的正式记录。",
            )
        if _integer(record.get("year")) != year or _integer(record.get("month")) != month:
            raise MonthlyRollupError(
                "SNAPSHOT_RECORD_PERIOD_MISMATCH",
                "月度快照记录与目标年月不一致。",
            )
        sanitized.append(_snapshot_record(record, index))

    sanitized.sort(
        key=lambda item: (
            str(item.get("complaint_date") or ""),
            str(item.get("record_key") or ""),
        )
    )
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "year": year,
        "month": month,
        "snapshot_format": SNAPSHOT_FORMAT,
        "payload": {
            "record_count": len(sanitized),
            "records": sanitized,
        },
    }


def render_monthly_rollup(
    request: dict[str, Any],
) -> dict[str, Any]:
    """Render the year-to-month cumulative outputs without any AI dependency."""

    normalized = _validate_rollup_request(request)
    year = normalized["year"]
    target_month = normalized["target_month"]
    output_dir = normalized["output_dir"]
    snapshot_entries = normalized["snapshots"]

    records: list[dict[str, Any]] = []
    used_months: list[int] = []
    snapshot_hashes: list[dict[str, Any]] = []
    for entry in snapshot_entries:
        payload = _read_and_validate_snapshot(
            entry["path"],
            expected_hash=entry["sha256"],
            expected_size=entry["size"],
            expected_year=year,
            expected_month=entry["month"],
            target_month=target_month,
        )
        records.extend(payload["payload"]["records"])
        used_months.append(entry["month"])
        snapshot_hashes.append(
            {
                "snapshot_id": entry["snapshot_id"],
                "month": entry["month"],
                "sha256": entry["sha256"],
            }
        )

    records.sort(
        key=lambda item: (
            _integer(item.get("year")) or 9999,
            _integer(item.get("month")) or 99,
            str(item.get("complaint_date") or ""),
            str(item.get("record_key") or ""),
        )
    )
    _assert_staging_directory(output_dir)
    temp_dir = Path(tempfile.mkdtemp(prefix=".after_sales_rollup_", dir=output_dir))
    try:
        paths = _render_outputs(
            records,
            temp_dir,
            year=year,
            target_month=target_month,
        )
        outputs: list[dict[str, Any]] = []
        for artifact in paths:
            final_path = output_dir / artifact["path"].name
            os.replace(artifact["path"], final_path)
            outputs.append(
                {
                    "type": artifact["type"],
                    "path": str(final_path),
                    "label": artifact["label"],
                    "mime_type": artifact["mime_type"],
                    "sha256": file_sha256(final_path),
                }
            )
    except MonthlyRollupError:
        raise
    except Exception as exc:
        raise MonthlyRollupError(
            "ROLLUP_RENDER_FAILED",
            "售后年度累计成果生成失败，请检查快照和暂存目录后重试。",
        ) from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "schema_version": ROLLUP_SCHEMA_VERSION,
        "transaction_id": normalized["transaction_id"],
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "status": "success",
        "year": year,
        "target_month": target_month,
        "used_months": used_months,
        "snapshot_hashes": snapshot_hashes,
        "record_count": len(records),
        "network_call_count": 0,
        "outputs": outputs,
        "error": None,
    }


def run_rollup_request(request_path: Path, response_path: Path) -> int:
    """CLI adapter that always returns a stable UTF-8 response document."""

    transaction_id = "invalid-request"
    year = 2000
    target_month = 1
    if not response_path.is_absolute():
        return 2
    try:
        _assert_staging_directory(response_path.parent)
        if not request_path.is_absolute():
            raise MonthlyRollupError(
                "ROLLUP_PATH_NOT_ABSOLUTE",
                "累计请求和响应路径必须是绝对路径。",
            )
        _assert_regular_file(request_path, "ROLLUP_REQUEST_PATH_INVALID")
        raw = json.loads(request_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            transaction_id = str(raw.get("transaction_id") or transaction_id)
            year = _integer(raw.get("year")) or year
            target_month = _integer(raw.get("target_month")) or target_month
        response = render_monthly_rollup(raw)
        _atomic_write_json(response_path, response)
        return 0
    except MonthlyRollupError as exc:
        _atomic_write_json(
            response_path,
            _error_response(
                transaction_id,
                year,
                target_month,
                exc.code,
                exc.public_message,
            ),
        )
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError):
        _atomic_write_json(
            response_path,
            _error_response(
                transaction_id,
                year,
                target_month,
                "ROLLUP_REQUEST_INVALID",
                "累计请求文件不是有效的 UTF-8 JSON。",
            ),
        )
        return 2


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_record(record: dict[str, Any], index: int) -> dict[str, Any]:
    result = {
        key: _json_value(record.get(key))
        for key in _SNAPSHOT_RECORD_FIELDS
        if key in record
    }
    digest = str(record.get("file_sha256") or "").strip().casefold()
    identity_material = "|".join(
        (
            digest,
            str(record.get("year") or ""),
            str(record.get("month") or ""),
            str(record.get("input_index") or index),
        )
    )
    result["record_key"] = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:24]
    suffix = Path(str(record.get("source_file") or "")).suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        suffix = ".xlsx"
    result["source_file"] = f"售后记录-{index:04d}{suffix}"
    result["sheet"] = ""
    result["issue_reason_summary"] = (
        f"{result.get('primary_issue_type') or '其他'}类售后问题（最终人工确认）"
    )
    result["warnings"] = []
    result["needs_review"] = False
    result["mandatory_review_pending"] = False
    result["analysis_error"] = ""
    return result


def _record_is_final(record: dict[str, Any]) -> bool:
    if not record.get("included_in_summary", True):
        return False
    return all(
        bool(record.get(key))
        for key in (
            "after_sales_fee_reviewed",
            "responsibility_reviewed",
            "complaint_type_reviewed",
            "manual_review_completed",
        )
    )


def _validate_rollup_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise MonthlyRollupError("ROLLUP_REQUEST_INVALID", "累计请求必须是 JSON 对象。")
    allowed = {
        "schema_version",
        "transaction_id",
        "module_id",
        "module_version",
        "year",
        "target_month",
        "offline_required",
        "snapshots",
        "snapshot_root",
        "output_dir",
        "configuration_identity",
    }
    if set(request) - allowed:
        raise MonthlyRollupError(
            "ROLLUP_REQUEST_FIELDS_INVALID",
            "累计请求包含模块合同未定义的字段。",
        )
    if request.get("schema_version") != ROLLUP_SCHEMA_VERSION:
        raise MonthlyRollupError(
            "ROLLUP_SCHEMA_VERSION_INVALID",
            "累计请求 schema_version 必须为 1.0。",
        )
    if request.get("module_id") != MODULE_ID:
        raise MonthlyRollupError(
            "ROLLUP_MODULE_MISMATCH",
            "累计请求模块与售后模块不一致。",
        )
    if request.get("module_version") != MODULE_VERSION:
        raise MonthlyRollupError(
            "ROLLUP_MODULE_VERSION_MISMATCH",
            "累计请求模块版本与售后模块不一致。",
        )
    if request.get("offline_required") is not True:
        raise MonthlyRollupError(
            "ROLLUP_OFFLINE_REQUIRED",
            "售后年度累计必须以强制离线模式运行。",
        )
    transaction_id = str(request.get("transaction_id") or "").strip()
    if not _stable_id(transaction_id):
        raise MonthlyRollupError(
            "ROLLUP_TRANSACTION_ID_INVALID",
            "累计请求缺少合法的 transaction_id。",
        )
    year = _integer(request.get("year"))
    target_month = _integer(request.get("target_month"))
    if year is None or not 2000 <= year <= 9999:
        raise MonthlyRollupError("ROLLUP_YEAR_INVALID", "累计请求年份不合法。")
    if target_month is None or not 1 <= target_month <= 12:
        raise MonthlyRollupError("ROLLUP_TARGET_MONTH_INVALID", "累计目标月份不合法。")

    raw_snapshot_root = request.get("snapshot_root")
    if not isinstance(raw_snapshot_root, str) or not Path(raw_snapshot_root).is_absolute():
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_ROOT_INVALID",
            "累计快照根目录必须是绝对路径。",
        )
    snapshot_root = _absolute_without_resolving(Path(raw_snapshot_root))
    if not snapshot_root.is_dir():
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_ROOT_INVALID",
            "累计快照根目录不存在或不可读取。",
        )
    _assert_path_chain_no_reparse(
        snapshot_root,
        "ROLLUP_SNAPSHOT_ROOT_REPARSE_POINT",
    )

    raw_output_dir = request.get("output_dir")
    if not isinstance(raw_output_dir, str) or not Path(raw_output_dir).is_absolute():
        raise MonthlyRollupError(
            "ROLLUP_STAGING_PATH_INVALID",
            "累计暂存输出目录必须是绝对路径。",
        )
    output_dir = _absolute_without_resolving(Path(raw_output_dir))
    _validate_configuration_identity(request.get("configuration_identity"))

    raw_snapshots = request.get("snapshots")
    if not isinstance(raw_snapshots, list) or not raw_snapshots:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOTS_EMPTY",
            "累计请求至少需要一个正式月度快照。",
        )
    snapshots: list[dict[str, Any]] = []
    previous_month = 0
    seen_months: set[int] = set()
    seen_snapshot_ids: set[str] = set()
    for raw in raw_snapshots:
        expected_fields = {
            "snapshot_id",
            "job_id",
            "module_id",
            "year",
            "month",
            "path",
            "size",
            "sha256",
        }
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_ENTRY_INVALID",
                "月度快照清单项格式不合法。",
            )
        snapshot_id = str(raw.get("snapshot_id") or "")
        if (
            not _stable_id(snapshot_id)
            or not _stable_id(str(raw.get("job_id") or ""))
        ):
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_ID_INVALID",
                "月度快照身份不合法。",
            )
        if raw.get("module_id") != MODULE_ID:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_MODULE_MISMATCH",
                "月度快照清单属于其他业务模块。",
            )
        if _integer(raw.get("year")) != year:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_YEAR_MISMATCH",
                "月度快照清单年份与累计请求不一致。",
            )
        month = _integer(raw.get("month"))
        if month is None or not 1 <= month <= target_month:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_MONTH_OUT_OF_RANGE",
                "月度快照月份超出目标月份范围。",
            )
        if month in seen_months:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_MONTH_DUPLICATE",
                "月度快照月份重复。",
            )
        if month <= previous_month:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_ORDER_INVALID",
                "月度快照必须按月份严格升序排列。",
            )
        if snapshot_id in seen_snapshot_ids:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_ID_INVALID",
                "月度快照身份重复。",
            )
        seen_snapshot_ids.add(snapshot_id)
        raw_path = raw.get("path")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_PATH_INVALID",
                "月度快照路径必须是绝对路径。",
            )
        snapshot_path = _absolute_without_resolving(Path(raw_path))
        _assert_contained(
            snapshot_path,
            snapshot_root,
            "ROLLUP_SNAPSHOT_PATH_OUTSIDE_ROOT",
        )
        size = _integer(raw.get("size"))
        if size is None or size < 0:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_SIZE_INVALID",
                "月度快照大小不合法。",
            )
        digest = str(raw.get("sha256") or "").strip().casefold()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_HASH_INVALID",
                "月度快照 SHA-256 格式不合法。",
            )
        snapshots.append(
            {
                "snapshot_id": snapshot_id,
                "job_id": str(raw["job_id"]),
                "month": month,
                "path": snapshot_path,
                "size": size,
                "sha256": digest,
            }
        )
        previous_month = month
        seen_months.add(month)

    return {
        "transaction_id": transaction_id,
        "year": year,
        "target_month": target_month,
        "snapshot_root": snapshot_root,
        "output_dir": output_dir,
        "snapshots": snapshots,
    }


def _read_and_validate_snapshot(
    path: Path,
    *,
    expected_hash: str,
    expected_size: int,
    expected_year: int,
    expected_month: int,
    target_month: int,
) -> dict[str, Any]:
    _assert_regular_file(path, "ROLLUP_SNAPSHOT_PATH_INVALID")
    if path.stat().st_size != expected_size:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_SIZE_MISMATCH",
            "月度快照大小校验失败。",
        )
    if file_sha256(path) != expected_hash:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_HASH_MISMATCH",
            "月度快照 SHA-256 校验失败。",
        )
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_INVALID",
            "月度快照不是有效的 UTF-8 JSON。",
        ) from exc
    if not isinstance(snapshot, dict):
        raise MonthlyRollupError("ROLLUP_SNAPSHOT_INVALID", "月度快照格式不合法。")
    if (
        snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION
        or snapshot.get("snapshot_format") != SNAPSHOT_FORMAT
    ):
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_FORMAT_INVALID",
            "月度快照版本或格式不受支持。",
        )
    if snapshot.get("module_id") != MODULE_ID:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_MODULE_MISMATCH",
            "月度快照属于其他业务模块。",
        )
    if _integer(snapshot.get("year")) != expected_year:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_YEAR_MISMATCH",
            "月度快照年份与累计请求不一致。",
        )
    month = _integer(snapshot.get("month"))
    if month != expected_month or month is None or month > target_month:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_MONTH_MISMATCH",
            "月度快照月份与清单或目标月份不一致。",
        )
    payload = snapshot.get("payload")
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        raise MonthlyRollupError(
            "ROLLUP_SNAPSHOT_RECORDS_INVALID",
            "月度快照没有有效的正式业务记录。",
        )
    for record in records:
        if not isinstance(record, dict) or not _record_is_final(record):
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_RECORD_NOT_FINAL",
                "月度快照包含未完成人工确认的业务记录。",
            )
        if (
            _integer(record.get("year")) != expected_year
            or _integer(record.get("month")) != expected_month
        ):
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_RECORD_PERIOD_MISMATCH",
                "月度快照业务记录的年月不一致。",
            )
        if str(record.get("primary_issue_type") or "") not in ISSUE_TYPES:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_COMPLAINT_TYPE_INVALID",
                "月度快照投诉类型不是允许的最终分类。",
            )
        source_file = str(record.get("source_file") or "")
        if not source_file or Path(source_file).name != source_file:
            raise MonthlyRollupError(
                "ROLLUP_SNAPSHOT_SOURCE_PATH_INVALID",
                "月度快照不得包含绝对输入路径。",
            )
    return snapshot


def _render_outputs(
    records: list[dict[str, Any]],
    output_dir: Path,
    *,
    year: int,
    target_month: int,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "summary": {
            "input_count": len(records),
            "processed_count": len(records),
            "failed_count": 0,
            "confirmation_count": 0,
        },
        "report_period": {
            "year": year,
            "target_month": target_month,
        },
    }
    artifacts = [
        (
            "master_summary_excel",
            "after_sales_master_summary.xlsx",
            "售后年度累计台账",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            lambda path: write_summary_workbook(records, path, {}),
        ),
        (
            "analysis_word",
            "after_sales_analysis_report.docx",
            "售后年度累计分析报告（Word）",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            lambda path: write_word_analysis_report(records, result, path),
        ),
        (
            "brand_share_chart_excel",
            "after_sales_brand_share.xlsx",
            "品牌方累计占比图表",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            lambda path: write_brand_share_workbook(records, path),
        ),
        (
            "issue_share_chart_excel",
            "after_sales_reason_share.xlsx",
            "售后原因累计占比图表",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            lambda path: write_issue_share_workbook(records, path),
        ),
        (
            "monthly_fee_chart_excel",
            "after_sales_monthly_fee.xlsx",
            "年度逐月售后费用图表",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            lambda path: write_annual_monthly_fee_workbook(records, path),
        ),
        (
            "yearly_chart_dashboard_excel",
            "after_sales_yearly_dashboard.xlsx",
            "售后年度累计看板",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            lambda path: write_yearly_chart_dashboard_workbook(records, path),
        ),
    ]
    rendered: list[dict[str, Any]] = []
    for artifact_type, filename, label, mime_type, writer in artifacts:
        path = output_dir / filename
        writer(path)
        rendered.append(
            {
                "type": artifact_type,
                "path": path,
                "label": label,
                "mime_type": mime_type,
            }
        )

    records_path = output_dir / "after_sales_records.json"
    _atomic_write_json(
        records_path,
        {
            "schema_version": "1.0",
            "module_id": MODULE_ID,
            "year": year,
            "target_month": target_month,
            "records": records,
        },
    )
    rendered.append(
        {
            "type": "business_records_json",
            "path": records_path,
            "label": "售后年度累计业务记录",
            "mime_type": "application/json",
        }
    )
    return rendered


def _stable_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9-]{6,64}", value))


def _validate_configuration_identity(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"version", "sha256"}:
        raise MonthlyRollupError(
            "ROLLUP_CONFIGURATION_IDENTITY_INVALID",
            "累计配置身份格式不合法。",
        )
    version = str(value.get("version") or "")
    digest = str(value.get("sha256") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", version) or not re.fullmatch(
        r"[0-9a-f]{64}", digest
    ):
        raise MonthlyRollupError(
            "ROLLUP_CONFIGURATION_IDENTITY_INVALID",
            "累计配置身份格式不合法。",
        )


def _assert_contained(path: Path, root: Path, code: str) -> None:
    try:
        common = os.path.commonpath(
            (os.path.normcase(os.fspath(path)), os.path.normcase(os.fspath(root)))
        )
    except ValueError as exc:
        raise MonthlyRollupError(code, "累计路径超出框架授权目录。") from exc
    if common != os.path.normcase(os.fspath(root)):
        raise MonthlyRollupError(code, "累计路径超出框架授权目录。")


def _assert_staging_directory(path: Path) -> None:
    if not path.is_absolute():
        raise MonthlyRollupError(
            "ROLLUP_STAGING_PATH_INVALID",
            "累计暂存输出目录必须是绝对路径。",
        )
    # Validate the nearest existing ancestor before creating anything. This
    # prevents ``mkdir`` from following a supplied junction and creating files
    # outside the framework-authorized staging tree.
    existing_ancestor = path
    while not existing_ancestor.exists() and existing_ancestor.parent != existing_ancestor:
        existing_ancestor = existing_ancestor.parent
    _assert_path_chain_no_reparse(
        existing_ancestor,
        "ROLLUP_STAGING_REPARSE_POINT",
    )
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MonthlyRollupError(
            "ROLLUP_STAGING_PATH_INVALID",
            "累计暂存输出目录无法创建或写入。",
        ) from exc
    _assert_path_chain_no_reparse(path, "ROLLUP_STAGING_REPARSE_POINT")


def _assert_regular_file(path: Path, code: str) -> None:
    _assert_path_chain_no_reparse(path, code)
    try:
        info = path.lstat()
    except OSError as exc:
        raise MonthlyRollupError(code, "累计请求引用的文件不存在或不可读取。") from exc
    _assert_not_reparse_point(path, code)
    if not stat.S_ISREG(info.st_mode):
        raise MonthlyRollupError(code, "累计请求引用的路径不是普通文件。")


def _assert_not_reparse_point(path: Path, code: str) -> None:
    try:
        info = path.lstat()
    except OSError:
        return
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if path.is_symlink() or attributes & reparse_flag:
        raise MonthlyRollupError(code, "累计路径不得使用符号链接或 junction。")


def _assert_path_chain_no_reparse(path: Path, code: str) -> None:
    current = path
    while True:
        _assert_not_reparse_point(current, code)
        if current.parent == current:
            return
        current = current.parent


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _error_response(
    transaction_id: str,
    year: int,
    target_month: int,
    code: str,
    message: str,
) -> dict[str, Any]:
    public_code = re.sub(r"[^a-z0-9_]", "_", code.casefold()).strip("_")
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", public_code):
        public_code = "rollup_failed"
    if not _stable_id(transaction_id):
        transaction_id = "invalid-request"
    if not 2000 <= year <= 9999:
        year = 2000
    if not 1 <= target_month <= 12:
        target_month = 1
    return {
        "schema_version": ROLLUP_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "status": "failed",
        "year": year,
        "target_month": target_month,
        "used_months": [],
        "snapshot_hashes": [],
        "record_count": 0,
        "network_call_count": 0,
        "outputs": [],
        "error": {"code": public_code, "message": message[:300]},
    }


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from after_sales_agent import MODULE_ID, MODULE_NAME, MODULE_VERSION
from after_sales_agent.analysis import write_analysis_report
from after_sales_agent.extractor import file_sha256, process_workbook
from after_sales_agent.report import write_summary_workbook
from after_sales_agent.rules import load_rules


def _module_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="after_sales")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version")
    subparsers.add_parser("self-check")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--job", required=True, help="任务JSON路径")
    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"{MODULE_ID} {MODULE_VERSION}")
        return 0
    if args.command == "self-check":
        return self_check()
    if args.command == "run":
        try:
            return run_job(Path(args.job))
        except Exception as exc:
            print(f"模块运行失败：{exc}", file=sys.stderr)
            return 3
    parser.print_help()
    return 2


def run_job(job_path: Path, runtime_config: dict[str, Any] | None = None) -> int:
    started_at = datetime.now().astimezone().isoformat()
    module_root = _module_root()
    try:
        with job_path.open("r", encoding="utf-8") as f:
            job = json.load(f)
    except Exception as exc:
        print(f"无法读取job.json：{exc}", file=sys.stderr)
        return 2

    try:
        _validate_job(job)
    except ValueError as exc:
        print(f"任务输入不合法：{exc}", file=sys.stderr)
        return 2

    output_dir = Path(job["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rules = load_rules(module_root, job.get("module_config_file"))
    # 统一工作台不会把 API Key 交给业务模块。只有独立网站通过进程内
    # runtime_config 调用本函数时才允许使用直连配置。
    api_config = (runtime_config or {}).get("api") if job.get("ai_enabled") else None
    progress_callback = (runtime_config or {}).get("progress_callback")
    result = _empty_result(job, rules, started_at)

    try:
        input_files = expand_inputs(job.get("input_files", []))
        result["summary"]["input_count"] = len(input_files)
        records: list[dict[str, Any]] = []
        seen_hashes: dict[str, str] = {}
        _notify_progress(
            progress_callback,
            {
                "phase": "开始分析",
                "message": f"共 {len(input_files)} 个 Excel，正在逐份处理",
                "total": len(input_files),
                "completed": 0,
                "succeeded": 0,
                "failed": 0,
                "current_file": "",
            },
        )

        for input_index, input_file in enumerate(input_files, start=1):
            progress_message = (
                f"正在处理第 {input_index}/{len(input_files)} 个文件：{input_file.name}"
            )
            _notify_progress(
                progress_callback,
                {
                    "phase": "智能辅助分析" if api_config else "离线规则分析",
                    "message": progress_message,
                    "total": len(input_files),
                    "completed": input_index - 1,
                    "succeeded": result["summary"]["processed_count"],
                    "failed": result["summary"]["failed_count"],
                    "current_file": input_file.name,
                },
            )
            file_result = {
                "source_file": str(input_file),
                "fingerprint": "",
                "status": "failed",
                "extracted_records": 0,
                "missing_fields": [],
                "anomaly_count": 0,
                "error": None,
            }
            try:
                if not input_file.exists():
                    raise FileNotFoundError(str(input_file))
                if input_file.suffix.lower() not in {".xlsx", ".xlsm"}:
                    raise ValueError("不支持的文件扩展名，仅支持 .xlsx/.xlsm")

                digest = file_sha256(input_file)
                file_result["fingerprint"] = digest
                duplicate_of = seen_hashes.get(digest)
                seen_hashes.setdefault(digest, str(input_file))

                record, anomalies, confirmations = process_workbook(input_file, rules, api_config)
                result["anomalies"].extend(
                    _normalize_anomalies(anomalies, len(result["anomalies"]))
                )
                result["confirmations"].extend(
                    _normalize_confirmations(confirmations, len(result["confirmations"]))
                )
                file_result["anomaly_count"] = len(anomalies)
                if record:
                    record["input_index"] = input_index
                    record["case_id"] = f"{job.get('job_id', 'batch')}-{input_index}"
                    record["analysis_status"] = (
                        "智能分析完成"
                        if record.get("issue_analysis_source") == "api"
                        else "离线规则分析完成"
                    )
                    record["analysis_error"] = ""
                    record["included_in_summary"] = True
                    if duplicate_of:
                        duplicate_warning = (
                            f"文件内容与 {Path(duplicate_of).name} 重复；"
                            "按用户保留两份的选择继续统计"
                        )
                        record.setdefault("warnings", []).append(duplicate_warning)
                        record["needs_review"] = True
                    records.append(record)
                    file_result["status"] = "success"
                    file_result["extracted_records"] = 1
                    result["summary"]["processed_count"] += 1
                else:
                    raise RuntimeError("未能从该工作簿生成售后记录")
            except Exception as exc:
                error_code, error_message = _classify_workbook_error(exc)
                public_error = f"{error_code}：{error_message}"
                file_result["status"] = "failed"
                file_result["error"] = public_error
                result["errors"].append(f"{input_file.name}：{public_error}")
                result["summary"]["failed_count"] += 1
                records.append(
                    _failed_record(
                        input_file,
                        input_index,
                        error_code,
                        error_message,
                        file_result.get("fingerprint"),
                    )
                )
            finally:
                result["file_results"].append(file_result)
                _notify_progress(
                    progress_callback,
                    {
                        "phase": "智能辅助分析" if api_config else "离线规则分析",
                        "message": f"已完成 {input_index}/{len(input_files)} 个文件",
                        "total": len(input_files),
                        "completed": input_index,
                        "succeeded": result["summary"]["processed_count"],
                        "failed": result["summary"]["failed_count"],
                        "current_file": input_file.name,
                    },
                )

        answered_confirmation_ids: set[str] = set()
        if job.get("phase") == "finalize":
            answered_confirmation_ids = _apply_confirmation_answers(
                records,
                result["confirmations"],
                Path(job["confirmation_file"]),
            )
            result["confirmations"] = [
                item
                for item in result["confirmations"]
                if item["confirmation_id"] not in answered_confirmation_ids
            ]

        _notify_progress(
            progress_callback,
            {
                "phase": "生成汇总表",
                "message": f"{len(input_files)} 个输入文件已全部对账，正在写入最终 Excel",
                "total": len(input_files),
                "completed": len(input_files),
                "succeeded": result["summary"]["processed_count"],
                "failed": result["summary"]["failed_count"],
                "current_file": "",
            },
        )
        result["summary"]["anomaly_count"] = len(result["anomalies"])
        result["summary"]["confirmation_count"] = len(result["confirmations"])
        result["status"] = decide_status(result)
        summary_path = output_dir / "after_sales_summary.xlsx"
        detail_path = output_dir / "after_sales_records.json"
        analysis_path = output_dir / "after_sales_analysis.md"
        write_summary_workbook(records, summary_path, rules)
        with detail_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        write_analysis_report(records, result, analysis_path)

        result["outputs"] = [
            {
                "type": "summary_excel",
                "path": str(summary_path),
                "label": "售后年度统计表",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
            {
                "type": "records_json",
                "path": str(detail_path),
                "label": "售后结构化明细",
                "mime_type": "application/json",
            },
            {
                "type": "analysis_markdown",
                "path": str(analysis_path),
                "label": "售后分析报告",
                "mime_type": "text/markdown",
            },
        ]
        result["analysis_summary"] = (
            f"已对账 {len(input_files)} 个输入文件，成功处理 "
            f"{result['summary']['processed_count']} 个，失败 "
            f"{result['summary']['failed_count']} 个；已生成三类金额汇总、分析图表和分析报告。"
        )
        return 0
    finally:
        result["finished_at"] = datetime.now().astimezone().isoformat()
        result_path = output_dir / "result.json"
        with result_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


def _notify_progress(callback: Any, payload: dict[str, Any]) -> None:
    if not callable(callback):
        total = max(int(payload.get("total") or 0), 1)
        completed = max(0, min(int(payload.get("completed") or 0), total))
        message = str(payload.get("message") or payload.get("phase") or "处理中")
        print(
            json.dumps(
                {
                    "type": "progress",
                    "percent": int(completed * 100 / total),
                    "message": message,
                },
                # 工作台按 UTF-8 逐行解析进度协议。冻结后的 Windows 控制台可能
                # 仍使用 GBK，因此协议层只输出 ASCII JSON 转义，避免中文消息
                # 被控制台编码成非 UTF-8 字节；JSON 解码后中文内容保持不变。
                ensure_ascii=True,
            ),
            flush=True,
        )
        return
    try:
        callback(payload)
    except Exception:
        # 进度展示不能影响 Excel 分析和汇总本身。
        return


def _validate_job(job: Any) -> None:
    if not isinstance(job, dict):
        raise ValueError("job.json 顶层必须是 JSON 对象")
    allowed_keys = {
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
    unexpected = sorted(set(job) - allowed_keys)
    if unexpected:
        raise ValueError(f"存在合同未定义字段：{', '.join(unexpected)}")
    if job.get("schema_version") != "1.0":
        raise ValueError("schema_version 必须为 1.0")
    if job.get("module_id") != MODULE_ID:
        raise ValueError(f"module_id 必须为 {MODULE_ID}")
    if job.get("phase") not in {"draft", "finalize"}:
        raise ValueError("phase 必须为 draft 或 finalize")
    if job.get("run_mode") not in {"single", "batch", "incremental"}:
        raise ValueError("run_mode 不受支持")
    input_files = job.get("input_files")
    if not isinstance(input_files, list) or not input_files:
        raise ValueError("input_files 至少需要一个文件")
    path_values = [*input_files, job.get("output_dir")]
    path_values.extend(
        job.get(key)
        for key in ("module_config_file", "confirmation_file", "service_response_file")
        if job.get(key)
    )
    if any(not isinstance(value, str) or not Path(value).is_absolute() for value in path_values):
        raise ValueError("所有任务路径都必须是绝对路径")
    if job.get("phase") == "finalize" and (
        not job.get("parent_job_id") or not job.get("confirmation_file")
    ):
        raise ValueError("finalize 阶段必须提供 parent_job_id 和 confirmation_file")


def _normalize_anomalies(items: list[dict[str, Any]], offset: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=offset + 1):
        severity = str(item.get("severity") or "warning")
        if severity not in {"info", "warning", "critical"}:
            severity = "warning"
        normalized.append(
            {
                "anomaly_id": f"A-{index:04d}",
                "severity": severity,
                "field": str(item.get("field") or "workbook"),
                "value": item.get("value"),
                "rule_id": item.get("rule_id"),
                "message": str(item.get("message") or "售后工作簿存在需要复核的异常"),
                "suggestion": item.get("suggestion"),
                "source": _source_ref(item),
            }
        )
    return normalized


def _normalize_confirmations(items: list[dict[str, Any]], offset: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=offset + 1):
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        normalized.append(
            {
                "confirmation_id": f"C-{index:04d}",
                "field": str(item.get("field") or "unknown"),
                "reason": str(item.get("reason") or "需要人工复核"),
                "suggested_value": item.get("suggested_value"),
                "options": list(item.get("options") or []),
                "confidence": max(0.0, min(confidence, 1.0)),
                "blocking": bool(item.get("blocking")),
                "batch_applicable": bool(item.get("batch_applicable", True)),
                "rememberable": bool(item.get("rememberable", True)),
                "source": _source_ref(item),
            }
        )
    return normalized


def _source_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": str(item.get("source_file") or ""),
        "sheet": str(item["sheet"]) if item.get("sheet") else None,
        "cell_or_range": str(item["cell_or_range"]) if item.get("cell_or_range") else None,
    }


def _apply_confirmation_answers(
    records: list[dict[str, Any]],
    confirmations: list[dict[str, Any]],
    confirmation_path: Path,
) -> set[str]:
    try:
        payload = json.loads(confirmation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"无法读取人工确认文件：{exc}") from exc
    raw_answers = payload.get("answers") if isinstance(payload, dict) else None
    if not isinstance(raw_answers, list):
        raise ValueError("人工确认文件缺少 answers 数组")
    answers = {
        str(item.get("confirmation_id")): item.get("value")
        for item in raw_answers
        if isinstance(item, dict) and item.get("confirmation_id")
    }
    answered: set[str] = set()
    for prompt in confirmations:
        confirmation_id = prompt["confirmation_id"]
        if confirmation_id not in answers:
            continue
        answered.add(confirmation_id)
        source_file = prompt.get("source", {}).get("source_file")
        record = next(
            (item for item in records if str(item.get("source_file")) == str(source_file)),
            None,
        )
        if record is None:
            continue
        _apply_record_value(record, prompt["field"], answers[confirmation_id])
        record["reviewed"] = True
    return answered


def _apply_record_value(record: dict[str, Any], field: str, value: Any) -> None:
    if field in {"brand", "brand_name"}:
        record["brand"] = str(value or "未知").strip() or "未知"
        record["brand_confidence"] = 1.0
        return
    if field == "issue_types":
        if isinstance(value, list):
            issue_types = [str(item).strip() for item in value if str(item).strip()]
        else:
            issue_types = [
                item.strip() for item in re.split(r"[,，/、]", str(value or "")) if item.strip()
            ]
        if issue_types:
            record["issue_types"] = issue_types
            record["primary_issue_type"] = issue_types[0]
            record["issue_confidence"] = 1.0
        return
    if field == "primary_issue_type":
        primary = str(value or "").strip()
        if primary:
            record["primary_issue_type"] = primary
            current = (
                record.get("issue_types") if isinstance(record.get("issue_types"), list) else []
            )
            record["issue_types"] = [primary, *[item for item in current if item != primary]]
            record["issue_confidence"] = 1.0
        return
    amount_fields = {
        "fee_amount": "enterprise_cost",
        "cost": "enterprise_cost",
        "enterprise_cost_amount": "enterprise_cost",
        "internal_accountability_amount": "internal_accountability",
        "external_borne_amount": "external_borne",
    }
    if field in amount_fields:
        prefix = amount_fields[field]
        text = str(value or "").replace(",", "").replace("元", "").strip()
        if not text:
            record[f"{prefix}_amount"] = None
            record[f"{prefix}_status"] = "not_found"
            record[f"{prefix}_evidence"] = "竹简工作台人工复核：金额留空"
            record[f"{prefix}_reviewed"] = True
            if prefix == "enterprise_cost":
                record["fee_amount"] = None
                record["cost"] = None
                record["fee_status"] = "not_found"
                record["cost_included"] = False
            return
        amount = float(text)
        record.update(
            {
                f"{prefix}_amount": amount,
                f"{prefix}_status": "exact",
                f"{prefix}_evidence": "竹简工作台人工复核值",
                f"{prefix}_reviewed": True,
            }
        )
        if prefix == "enterprise_cost":
            record.update(
                {
                    "fee_amount": amount,
                    "cost": amount,
                    "fee_status": "exact",
                    "cost_included": True,
                    "cost_status": "人工复核确认",
                    "cost_evidence": "竹简工作台人工复核值",
                }
            )
        return
    if field == "complaint_date":
        text = str(value or "").strip()
        record["complaint_date_raw"] = text
        record["complaint_date"] = text
        year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", text)
        month_match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*月", text)
        if month_match is None:
            month_match = re.search(r"(?:20\d{2})[-/.](1[0-2]|0?[1-9])(?:[-/.]|$)", text)
        record["year"] = int(year_match.group(1)) if year_match else None
        record["month"] = int(month_match.group(1)) if month_match else None
        return
    if field in {"closed", "resolution_status", "case_status"}:
        text = str(value or "").strip()
        closed = value is True or text in {"是", "已解决", "已关闭", "完成", "结案"}
        record["closed"] = closed
        record["resolution_status"] = "已解决" if closed else (text or "未解决")
        record["case_status"] = "已关闭" if closed else "待确认"
        return
    if field and field != "api_config":
        record[field] = value


def expand_inputs(input_files: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in input_files:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(p for p in path.rglob("*.xlsx") if not p.name.startswith("~$")))
            paths.extend(sorted(p for p in path.rglob("*.xlsm") if not p.name.startswith("~$")))
        else:
            paths.append(path)
    return paths


def _failed_record(
    path: Path,
    input_index: int,
    error_code: str,
    error_message: str,
    digest: str | None,
) -> dict[str, Any]:
    """保留失败文件的对账行，但不把未知业务数据计入售后统计。"""
    return {
        "input_index": input_index,
        "source_file": path.name,
        "sheet": "",
        "file_sha256": digest or "",
        "analysis_status": "分析失败",
        "analysis_error": f"{error_code}：{error_message}",
        "error_code": error_code,
        "included_in_summary": False,
        "customer": "",
        "brand": "未知",
        "brand_confidence": 0.0,
        "issue_types": ["其他"],
        "primary_issue_type": "其他",
        "issue_reason_summary": f"文件未能完成分析：{error_message}",
        "issue_confidence": 0.0,
        "cost": None,
        "fee_amount": None,
        "enterprise_cost_amount": None,
        "enterprise_cost_status": "not_found",
        "enterprise_cost_evidence": "文件分析失败，无法识别企业售后成本",
        "enterprise_cost_reviewed": False,
        "internal_accountability_amount": None,
        "internal_accountability_status": "not_found",
        "internal_accountability_evidence": "文件分析失败，无法识别内部责任扣款",
        "internal_accountability_reviewed": False,
        "external_borne_amount": None,
        "external_borne_status": "not_found",
        "external_borne_evidence": "文件分析失败，无法识别外部承担金额",
        "external_borne_reviewed": False,
        "fee_currency": "CNY",
        "fee_status": "needs_review",
        "cost_included": False,
        "cost_status": "分析失败，费用未知",
        "cost_evidence": "",
        "cost_items": [],
        "closed": False,
        "year": None,
        "month": None,
        "warnings": [f"文件分析失败：{error_message}"],
        "needs_review": True,
        "reviewed": False,
        "source_cells": {},
    }


def _classify_workbook_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, (BadZipFile, InvalidFileException, EOFError)):
        return (
            "WORKBOOK_INVALID_OR_CORRUPTED",
            "工作簿损坏或不是有效的 XLSX 文件，请重新导出后再试。",
        )
    if isinstance(exc, FileNotFoundError):
        return "INPUT_FILE_NOT_FOUND", "输入文件不存在或已被移动，请重新选择后再试。"
    if isinstance(exc, PermissionError):
        return "WORKBOOK_ACCESS_DENIED", "工作簿正在被占用或没有读取权限，请关闭文件后再试。"
    if isinstance(exc, ValueError) and "不支持的文件扩展名" in str(exc):
        return "WORKBOOK_FORMAT_UNSUPPORTED", "仅支持有效的 XLSX 或 XLSM 工作簿。"
    return "WORKBOOK_PROCESSING_FAILED", "工作簿处理失败，请检查文件内容并重新导出后再试。"


def decide_status(result: dict[str, Any]) -> str:
    if result["summary"]["processed_count"] == 0:
        return "failed"
    if result["summary"]["failed_count"] or result["summary"]["skipped_count"]:
        return "partial_success"
    if result["summary"]["confirmation_count"]:
        return "needs_confirmation"
    return "success"


def _empty_result(job: dict[str, Any], rules: dict[str, Any], started_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "job_id": job.get("job_id", ""),
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "status": "failed",
        "rule_version": rules.get("rule_version"),
        "summary": {
            "input_count": 0,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 0,
            "confirmation_count": 0,
        },
        "anomalies": [],
        "confirmations": [],
        "outputs": [],
        "file_results": [],
        "service_requests": [],
        "analysis_summary": None,
        "errors": [],
        "started_at": started_at,
        "finished_at": None,
    }


def self_check() -> int:
    with tempfile.TemporaryDirectory(prefix="after_sales_self_check_") as tmp:
        tmp_path = Path(tmp)
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        _create_sample_workbook(
            input_dir / "sample.xlsx",
            customer="自测客户",
            brand_text="桃花江品牌",
            date_text="2026.5.10",
            feedback="地板出现开裂、发霉。",
            solution="总计2930元，此费由二厂承担，已安排更换处理。",
        )
        job = {
            "schema_version": "1.0",
            "job_id": "self-check",
            "module_id": MODULE_ID,
            "phase": "draft",
            "run_mode": "batch",
            "input_files": [str(input_dir / "sample.xlsx")],
            "output_dir": str(output_dir),
            "module_config_file": None,
            "ai_enabled": False,
            "allowed_knowledge_scopes": [],
            "parent_job_id": None,
            "confirmation_file": None,
            "service_response_file": None,
        }
        job_path = tmp_path / "job.json"
        with job_path.open("w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
        exit_code = run_job(job_path)
        result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
        if exit_code != 0 or result["summary"]["processed_count"] != 1:
            print("self-check failed", file=sys.stderr)
            return 3
        print(f"{MODULE_NAME} self-check passed: {output_dir / 'after_sales_summary.xlsx'}")
        return 0


def _create_sample_workbook(
    path: Path, customer: str, brand_text: str, date_text: str, feedback: str, solution: str
) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "售后单"
    rows = [
        ["售后方案申请表", None, None, None],
        ["客户/项目", customer, "地点", "自测地点"],
        ["销售/代表", "自测销售", "日期", date_text],
        ["产品名称", brand_text, "规格", "1860*139*18"],
        ["订单", "FZ自测20260501-001N", "交货日期", "2026.5.1"],
        ["反馈内容", feedback, None, None],
        ["方案申请明细", "客户要求更换。", None, None],
        ["售后负责人调查情况", "经确认属于产品性能问题。", None, None],
        ["售后解决方案", solution, None, None],
    ]
    for row in rows:
        ws.append(row)
    wb.save(path)


if __name__ == "__main__":
    raise SystemExit(main())

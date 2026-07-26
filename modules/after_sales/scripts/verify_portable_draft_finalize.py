"""Run a no-network draft -> denied-AI -> finalize check against the frozen module."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _run(runtime: Path, job_path: Path) -> None:
    completed = subprocess.run(
        [str(runtime), "run", "--job", str(job_path)],
        capture_output=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.decode("utf-8", errors="replace")
            or f"便携运行时退出码：{completed.returncode}"
        )
    for line in completed.stdout.decode("utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") != "progress":
            raise ValueError("便携运行时输出了非进度协议内容")


def _run_rollup(runtime: Path, request_path: Path, response_path: Path) -> None:
    completed = subprocess.run(
        [
            str(runtime),
            "rollup",
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        capture_output=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.decode("utf-8", errors="replace")
            or f"便携累计运行时退出码：{completed.returncode}"
        )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) != 4:
        print("用法：verify_portable_draft_finalize.py <exe> <样例Excel> <工作目录>")
        return 2
    runtime = Path(sys.argv[1]).resolve()
    source = Path(sys.argv[2]).resolve()
    work = Path(sys.argv[3]).resolve()
    if not runtime.is_file() or not source.is_file():
        raise FileNotFoundError("便携运行时或脱敏样例不存在")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    draft_output = work / "output-draft"
    draft_job = {
        "schema_version": "1.0",
        "job_id": "portable-v130-draft",
        "module_id": "after_sales",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(source)],
        "output_dir": str(draft_output),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    draft_job_path = work / "job-draft.json"
    _write_json(draft_job_path, draft_job)
    _run(runtime, draft_job_path)
    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    if draft.get("module_version") != "1.3.0":
        raise AssertionError("便携运行时不是售后模块 1.3.0")
    if draft.get("confirmations"):
        raise AssertionError("第一次 draft 不应在框架 AI 调用前生成业务确认")
    requests = draft.get("service_requests")
    if not isinstance(requests, list) or not requests:
        raise AssertionError("草稿未生成统一AI辅助请求")
    service_path = work / "service-response.json"
    _write_json(
        service_path,
        {
            "schema_version": "1.0",
            "task_id": "portable-v130-draft",
            "module_id": "after_sales",
            "responses": [
                {
                    "request_id": item["request_id"],
                    "service": "ai",
                    "status": "denied",
                    "text": None,
                }
                for item in requests
            ],
        },
    )
    rebound_job = {
        **draft_job,
        "ai_enabled": True,
        "service_response_file": str(service_path),
    }
    _write_json(draft_job_path, rebound_job)
    _run(runtime, draft_job_path)
    rebound = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    if rebound.get("service_requests"):
        raise AssertionError("第二次 draft 不应再次申请 AI 服务")
    fields = {item.get("field") for item in rebound.get("confirmations", [])}
    if not {"售后费用", "责任工厂", "投诉类型"} <= fields:
        raise AssertionError("第二次 draft 缺少三项强制人工复核")
    rebound_records = json.loads(
        (draft_output / "after_sales_records.json").read_text(encoding="utf-8")
    )
    if not rebound_records or "降级" not in str(
        rebound_records[0].get("analysis_status") or ""
    ):
        raise AssertionError("拒绝AI后未保留离线降级结果")

    confirmation_path = work / "confirmation.json"
    _write_json(
        confirmation_path,
        {
            "schema_version": "1.0",
            "job_id": "portable-v130-draft",
            "answers": [
                {
                    "confirmation_id": item["confirmation_id"],
                    "value": item.get("suggested_value"),
                }
                for item in rebound["confirmations"]
            ],
        },
    )
    final_output = work / "output-final"
    final_job = {
        **rebound_job,
        "job_id": "portable-v130-final",
        "phase": "finalize",
        "output_dir": str(final_output),
        "ai_enabled": False,
        "parent_job_id": "portable-v130-draft",
        "confirmation_file": str(confirmation_path),
        "service_response_file": str(service_path),
    }
    final_job_path = work / "job-finalize.json"
    _write_json(final_job_path, final_job)
    _run(runtime, final_job_path)
    final = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    records = json.loads(
        (final_output / "after_sales_records.json").read_text(encoding="utf-8")
    )
    if final.get("status") != "success":
        raise AssertionError(f"便携 finalize 未成功：{final.get('status')}")
    if final.get("service_requests"):
        raise AssertionError("finalize 不得再次申请 AI 服务")
    if not records or "降级" not in str(records[0].get("analysis_status") or ""):
        raise AssertionError("拒绝AI后未标记离线降级")
    expected_outputs = {
        "after_sales_master_summary.xlsx",
        "after_sales_records.json",
        "after_sales_analysis_report.docx",
        "after_sales_brand_share.xlsx",
        "after_sales_reason_share.xlsx",
        "after_sales_monthly_fee.xlsx",
        "after_sales_yearly_dashboard.xlsx",
    }
    if not expected_outputs <= {path.name for path in final_output.iterdir()}:
        raise AssertionError("便携 finalize 输出不完整")
    snapshot_path = final_output / "after_sales_monthly_snapshot.json"
    if not snapshot_path.is_file():
        raise AssertionError("便携 finalize 未生成确认后月度快照")
    snapshot_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    rollup_output = work / "rollup-output"
    rollup_request_path = work / "rollup-request.json"
    rollup_response_path = work / "rollup-response.json"
    _write_json(
        rollup_request_path,
        {
            "schema_version": "1.0",
            "request_id": "portable-v130-rollup",
            "module_id": "after_sales",
            "module_version": "1.3.0",
            "year": 2026,
            "target_month": 5,
            "offline_required": True,
            "snapshots": [
                {
                    "month": 5,
                    "path": str(snapshot_path),
                    "sha256": snapshot_hash,
                }
            ],
            "staging_output_dir": str(rollup_output),
            "rule_snapshot_id": "portable-rules",
            "experience_snapshot_id": None,
            "business_config_snapshot_id": "portable-config",
        },
    )
    _run_rollup(runtime, rollup_request_path, rollup_response_path)
    rollup = json.loads(rollup_response_path.read_text(encoding="utf-8"))
    if rollup.get("status") != "success" or rollup.get("used_months") != [5]:
        raise AssertionError(f"便携离线累计未成功：{rollup}")
    if len(rollup.get("outputs", [])) != 7:
        raise AssertionError("便携离线累计输出不完整")
    print("便携版 draft→拒绝AI→finalize→月度快照→离线累计闭环通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

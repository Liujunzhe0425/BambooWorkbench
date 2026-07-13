import argparse
import hashlib
import json
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from core.contracts.confirmation import ConfirmationBundle
from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult

from .artifacts import create_artifacts
from .scenarios import scenario_for


def now() -> str:
    return datetime.now().astimezone().isoformat()


def run(module_id: str, job_path: Path) -> int:
    try:
        job = JobRequest.model_validate_json(job_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        print(f"invalid job request: {type(error).__name__}", file=sys.stderr)
        return 2
    if job.module_id.value != module_id:
        print(
            f"module-id mismatch: command={module_id}, job={job.module_id.value}",
            file=sys.stderr,
        )
        return 2
    scenario = scenario_for(job.input_files)
    try:
        _validate_finalize_confirmation(job, scenario)
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        print(f"invalid confirmation bundle: {type(error).__name__}", file=sys.stderr)
        return 2
    try:
        return _run_validated_job(module_id, job, scenario)
    except Exception:
        print("mock runtime failed", file=sys.stderr)
        return 3


def _validate_finalize_confirmation(job: JobRequest, scenario: str) -> None:
    if job.phase.value != "finalize":
        return
    confirmation_path = Path(job.confirmation_file or "")
    bundle = ConfirmationBundle.model_validate_json(
        confirmation_path.read_text(encoding="utf-8")
    )
    if bundle.job_id != job.parent_job_id:
        raise ValueError("confirmation parent does not match finalize parent")
    if scenario == "confirm" and not any(
        answer.confirmation_id == "mock-confirm-1" for answer in bundle.answers
    ):
        raise ValueError("required mock confirmation answer is missing")


def _run_validated_job(module_id: str, job: JobRequest, scenario: str) -> int:
    output_dir = Path(job.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    status = "success"
    confirmations: list[dict[str, object]] = []
    failed_count = 0
    errors: list[str] = []
    service_requests: list[dict[str, object]] = []
    include_outputs = True
    if scenario == "confirm" and job.phase.value == "draft":
        status = "needs_confirmation"
        confirmations = [
            {
                "confirmation_id": "mock-confirm-1",
                "field": "mock_field",
                "reason": "模拟边界问题",
                "suggested_value": "建议值",
                "options": ["建议值", "人工值"],
                "confidence": 0.5,
                "blocking": True,
                "batch_applicable": True,
                "rememberable": False,
                "source": {
                    "source_file": job.input_files[0],
                    "sheet": None,
                    "cell_or_range": None,
                },
            }
        ]
    elif scenario == "partial":
        status = "partial_success"
        failed_count = 1
        errors = ["模拟单文件失败"]
    elif scenario == "fail":
        status = "failed"
        failed_count = len(job.input_files)
        errors = ["模拟任务失败"]
        include_outputs = False
    elif scenario == "invalid":
        (output_dir / "result.json").write_text("{invalid", encoding="utf-8")
        return 0
    elif scenario == "ai":
        service_requests = [
            {
                "request_id": "ai-1",
                "service": "ai",
                "scope": None,
                "purpose": "生成模拟分析",
                "payload": {"metrics": [1, 2, 3]},
                "requires_user_consent": True,
            }
        ]
    elif scenario == "knowledge":
        service_requests = [
            {
                "request_id": "kb-1",
                "service": "knowledge",
                "scope": module_id,
                "purpose": "检索模拟规则",
                "payload": {"query": "异常处理"},
                "requires_user_consent": False,
            }
        ]

    if scenario == "crash":
        print("simulated module crash", file=sys.stderr)
        return 3
    if scenario == "timeout":
        time.sleep(120)

    started = now()
    print(
        json.dumps(
            {"type": "progress", "percent": 25, "message": "读取模拟输入"},
            ensure_ascii=False,
        ),
        flush=True,
    )
    artifacts = create_artifacts(output_dir, module_id) if include_outputs else []

    file_results = []
    for index, path in enumerate(job.input_files):
        file_failed = scenario == "fail" or (scenario == "partial" and index == 0)
        file_results.append(
            {
                "source_file": path,
                "fingerprint": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "status": "failed" if file_failed else "success",
                "extracted_records": 0 if file_failed else 1,
                "missing_fields": [],
                "anomaly_count": 0,
                "error": errors[0] if file_failed else None,
            }
        )

    result = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "module_id": module_id,
        "module_version": "0.1.0",
        "status": status,
        "rule_version": "mock-1.0",
        "summary": {
            "input_count": len(job.input_files),
            "processed_count": len(job.input_files) - failed_count,
            "skipped_count": 0,
            "failed_count": failed_count,
            "anomaly_count": 0,
            "confirmation_count": len(confirmations),
        },
        "anomalies": [],
        "confirmations": confirmations,
        "outputs": artifacts,
        "file_results": file_results,
        "service_requests": service_requests,
        "analysis_summary": "模拟模块运行成功",
        "errors": errors,
        "started_at": started,
        "finished_at": now(),
    }
    validated = ModuleResult.model_validate(result)
    (output_dir / "result.json").write_text(
        validated.model_dump_json(indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"type": "progress", "percent": 100, "message": "模拟处理完成"},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--module-id", required=True, choices=["moisture", "boiling", "after_sales"]
    )
    parser.add_argument("command", choices=["version", "self-check", "run"])
    parser.add_argument("--job", type=Path)
    args = parser.parse_args(arguments)
    if args.command == "version":
        print("0.1.0")
        return 0
    if args.command == "self-check":
        print("ok")
        return 0
    if args.job is None:
        parser.error("run requires --job")
    return run(args.module_id, args.job.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

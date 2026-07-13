import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult

from .artifacts import create_artifacts
from .scenarios import scenario_for


def now() -> str:
    return datetime.now().astimezone().isoformat()


def run(module_id: str, job_path: Path) -> int:
    job = JobRequest.model_validate_json(job_path.read_text(encoding="utf-8"))
    output_dir = Path(job.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario = scenario_for(job.input_files)
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
    artifacts = create_artifacts(output_dir, module_id)
    print(
        json.dumps(
            {"type": "progress", "percent": 100, "message": "模拟处理完成"},
            ensure_ascii=False,
        ),
        flush=True,
    )

    confirmations: list[dict[str, object]] = []
    status = "success"
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

    result = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "module_id": module_id,
        "module_version": "0.1.0",
        "status": status,
        "rule_version": "mock-1.0",
        "summary": {
            "input_count": len(job.input_files),
            "processed_count": len(job.input_files),
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 0,
            "confirmation_count": len(confirmations),
        },
        "anomalies": [],
        "confirmations": confirmations,
        "outputs": artifacts,
        "file_results": [
            {
                "source_file": path,
                "fingerprint": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "status": "success",
                "extracted_records": 1,
                "missing_fields": [],
                "anomaly_count": 0,
                "error": None,
            }
            for path in job.input_files
        ],
        "service_requests": [],
        "analysis_summary": "模拟模块运行成功",
        "errors": [],
        "started_at": started,
        "finished_at": now(),
    }
    validated = ModuleResult.model_validate(result)
    (output_dir / "result.json").write_text(
        validated.model_dump_json(indent=2), encoding="utf-8"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--module-id", required=True, choices=["moisture", "boiling", "after_sales"]
    )
    parser.add_argument("command", choices=["version", "self-check", "run"])
    parser.add_argument("--job", type=Path)
    args = parser.parse_args()
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

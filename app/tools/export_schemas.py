import json
from pathlib import Path

from pydantic import BaseModel

from core.contracts.job import JobRequest
from core.contracts.manifest import ModuleManifest
from core.contracts.result import ModuleResult

MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("module-manifest.schema.json", ModuleManifest),
    ("job-request.schema.json", JobRequest),
    ("module-result.schema.json", ModuleResult),
)

EXAMPLES: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "module.json",
        {
            "schema_version": "1.0",
            "module_id": "moisture",
            "module_name": "示例模块",
            "module_version": "0.1.0",
            "entrypoint": "run_module.bat",
            "supported_extensions": [".csv"],
            "supports_single_file": True,
            "supports_batch": True,
            "supports_incremental": False,
            "requires_network": False,
        },
    ),
    (
        "job.json",
        {
            "schema_version": "1.0",
            "job_id": "20260713-0001",
            "module_id": "moisture",
            "phase": "draft",
            "run_mode": "single",
            "input_files": ["D:/BambooWorkbench/inbox/example.csv"],
            "output_dir": "D:/BambooWorkbench/tasks/20260713-0001",
            "module_config_file": None,
            "ai_enabled": False,
            "allowed_knowledge_scopes": [],
            "parent_job_id": None,
            "confirmation_file": None,
            "service_response_file": None,
        },
    ),
    (
        "result.json",
        {
            "schema_version": "1.0",
            "job_id": "20260713-0001",
            "module_id": "moisture",
            "module_version": "0.1.0",
            "status": "success",
            "rule_version": None,
            "summary": {
                "input_count": 1,
                "processed_count": 1,
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
            "started_at": "2026-07-13T09:00:00+08:00",
            "finished_at": "2026-07-13T09:00:01+08:00",
        },
    ),
)


def _write_json(path: Path, payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text + "\n")


def export_contracts(root: Path) -> list[Path]:
    schema_dir = root / "contracts" / "schemas"
    example_dir = root / "contracts" / "examples"
    schema_dir.mkdir(parents=True, exist_ok=True)
    example_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, model in MODELS:
        path = schema_dir / filename
        _write_json(path, model.model_json_schema())
        written.append(path)
    for filename, payload in EXAMPLES:
        path = example_dir / filename
        _write_json(path, payload)
        written.append(path)
    return written


if __name__ == "__main__":
    export_contracts(Path.cwd())

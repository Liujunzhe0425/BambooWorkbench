"""Run read-only local history acceptance without committing customer data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.contracts.result import ModuleResult


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _invoke(module_root: Path, job_path: Path) -> None:
    environment = dict(os.environ)
    environment["BAMBOO_PYTHON"] = sys.executable
    environment["BAMBOO_MODULE_PYTHON"] = sys.executable
    environment["PYTHON_EXE"] = sys.executable
    process = subprocess.run(
        [str(module_root / "run_module.bat"), "run", "--job", str(job_path)],
        cwd=module_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"{module_root.name} exited {process.returncode}: {process.stderr[-2000:]}"
        )


def _answer(
    prompt: dict[str, Any],
    replay_answers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    field = str(prompt.get("field") or "")
    confirmation_id = str(prompt["confirmation_id"])
    if confirmation_id in replay_answers:
        previous = replay_answers[confirmation_id]
        return {
            "confirmation_id": confirmation_id,
            "value": previous.get("value"),
            "apply_to_batch": bool(previous.get("apply_to_batch")),
            "remember_mapping": False,
        }
    if field == "default_year":
        value: object = 2026
        apply_to_batch = True
    elif prompt.get("suggested_value") is not None:
        value = prompt["suggested_value"]
        apply_to_batch = False
    elif len(prompt.get("options") or []) == 1:
        value = prompt["options"][0]
        apply_to_batch = False
    else:
        raise RuntimeError(
            "历史验收遇到无建议值的人工判断，必须由品质人员回答："
            f"{confirmation_id} / {field} / {prompt.get('reason')}"
        )
    return {
        "confirmation_id": confirmation_id,
        "value": value,
        "apply_to_batch": apply_to_batch,
        "remember_mapping": False,
    }


def _load_replay_answers(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(answer["confirmation_id"]): answer
        for answer in payload.get("answers", [])
        if isinstance(answer, dict) and answer.get("confirmation_id")
    }


def _scan_no_customer_path(outputs: list[Path], customer_root: Path) -> None:
    needles = {
        str(customer_root).encode("utf-8"),
        str(customer_root).replace("\\", "/").encode("utf-8"),
    }
    for output in outputs:
        if output.suffix.lower() == ".xlsx":
            with zipfile.ZipFile(output) as archive:
                blobs = [archive.read(name) for name in archive.namelist() if name.endswith(".xml")]
        else:
            blobs = [output.read_bytes()]
        if any(needle in blob for needle in needles for blob in blobs):
            raise AssertionError(f"customer absolute path leaked into {output.name}")


def _module_inputs(directory: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".xlsx", ".xlsm"}
        and not path.name.startswith("~$")
    )


def run_module(
    repository: Path,
    module_id: str,
    input_dir: Path,
    output_root: Path,
    answer_replay: Path | None = None,
) -> dict[str, Any]:
    module_root = repository / "modules" / module_id
    inputs = _module_inputs(input_dir)
    before = {path: _hash(path) for path in inputs}
    draft_id = f"history-{module_id}-draft-{uuid4().hex[:10]}"
    draft_output = output_root / module_id / "draft"
    draft_job_path = output_root / module_id / "draft-job.json"
    job: dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": draft_id,
        "module_id": module_id,
        "phase": "draft",
        "run_mode": "batch",
        "input_files": [str(path) for path in inputs],
        "output_dir": str(draft_output.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [module_id],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    _write_json(draft_job_path, job)
    _invoke(module_root, draft_job_path)
    draft_payload = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    draft = ModuleResult.model_validate(draft_payload)
    final = draft
    final_output = draft_output

    if draft.confirmations:
        replay_answers = _load_replay_answers(answer_replay)
        confirmation_path = output_root / module_id / "confirmation.json"
        _write_json(
            confirmation_path,
            {
                "schema_version": "1.0",
                "job_id": draft_id,
                "answers": [
                    _answer(item.model_dump(mode="json"), replay_answers)
                    for item in draft.confirmations
                ],
            },
        )
        final_output = output_root / module_id / "final"
        final_job_path = output_root / module_id / "final-job.json"
        final_job = {
            **job,
            "job_id": f"history-{module_id}-final-{uuid4().hex[:10]}",
            "phase": "finalize",
            "output_dir": str(final_output.resolve()),
            "parent_job_id": draft_id,
            "confirmation_file": str(confirmation_path.resolve()),
        }
        _write_json(final_job_path, final_job)
        _invoke(module_root, final_job_path)
        final_payload = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
        final = ModuleResult.model_validate(final_payload)

    after = {path: _hash(path) for path in inputs}
    if before != after:
        raise AssertionError(f"{module_id} modified a customer source file")
    if final.confirmations:
        raise AssertionError(f"{module_id} emitted follow-up confirmations")
    if final.summary.input_count != len(inputs):
        raise AssertionError(f"{module_id} input accounting mismatch")
    artifacts = [Path(item.path) for item in final.outputs]
    if not artifacts or any(not path.is_file() for path in artifacts):
        raise AssertionError(f"{module_id} output artifact is missing")
    _scan_no_customer_path(artifacts, input_dir.resolve())
    return {
        "input_count": len(inputs),
        "status": final.status.value,
        "processed_count": final.summary.processed_count,
        "skipped_count": final.summary.skipped_count,
        "failed_count": final.summary.failed_count,
        "anomaly_count": final.summary.anomaly_count,
        "draft_confirmations": len(draft.confirmations),
        "final_confirmations": len(final.confirmations),
        "outputs": [path.name for path in artifacts],
        "output_dir": str(final_output),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moisture", type=Path, required=True)
    parser.add_argument("--boiling", type=Path, required=True)
    parser.add_argument("--after-sales", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--moisture-answers", type=Path)
    parser.add_argument("--boiling-answers", type=Path)
    parser.add_argument("--after-sales-answers", type=Path)
    arguments = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    reports = {
        "moisture": run_module(
            repository,
            "moisture",
            arguments.moisture,
            arguments.output_root,
            arguments.moisture_answers,
        ),
        "boiling": run_module(
            repository,
            "boiling",
            arguments.boiling,
            arguments.output_root,
            arguments.boiling_answers,
        ),
        "after_sales": run_module(
            repository,
            "after_sales",
            arguments.after_sales,
            arguments.output_root,
            arguments.after_sales_answers,
        ),
    }
    expected_counts = {"moisture": 21, "boiling": 41, "after_sales": 13}
    for module_id, expected in expected_counts.items():
        if reports[module_id]["input_count"] != expected:
            raise AssertionError(
                f"{module_id} expected {expected} inputs, got {reports[module_id]['input_count']}"
            )
    report_path = arguments.output_root / "history-acceptance-summary.json"
    _write_json(report_path, reports)
    json.dump(reports, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

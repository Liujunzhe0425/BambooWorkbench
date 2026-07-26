import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import openpyxl
import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "boiling_module_rollup_tests",
    MODULE_ROOT / "src" / "boiling_module.py",
)
assert SPEC and SPEC.loader
boiling_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(boiling_module)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_sample(path, *, month=1, batch_no="MONTH-001"):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "水煮实验"
    sheet.append(
        ["批号", batch_no, "产品名称", "脱敏竹材", "规格型号", "100×100×10"]
    )
    sheet.append(
        ["压制日期", dt.date(2026, month, 3), "班长", "脱敏班长", "产品用途", "家具"]
    )
    sheet.append(
        [
            "检测日期",
            dt.date(2026, month, 16),
            "浸胶日期",
            dt.date(2026, month, 10),
            "订单号",
            "SANITIZED-ORDER",
        ]
    )
    sheet.cell(7, 1, "试件")
    sheet.cell(7, 2, "长度(mm)")
    sheet.cell(7, 3, "宽度(mm)")
    sheet.cell(7, 4, "煮前厚度(mm)")
    sheet.cell(7, 5, "重量(g)")
    sheet.cell(7, 6, "密度(g/cm³)")
    sheet.cell(7, 7, "煮后厚度(mm)")
    sheet.cell(7, 8, "膨胀率")
    sheet.cell(8, 1, "端1-1")
    sheet.cell(8, 2, 100)
    sheet.cell(8, 3, 100)
    sheet.cell(9, 5, 140)
    for row in range(8, 14):
        sheet.cell(row, 4, 10.0)
        sheet.cell(row, 7, 10.5)
    sheet.cell(14, 6, 1.4)
    sheet.cell(14, 8, 0.05)
    sheet.cell(
        17,
        1,
        "检测结论：密度检测合格，2h膨胀率检测合格，浸渍剥离检测合格",
    )
    workbook.save(path)


def make_job(sample, output, *, phase="draft", **extra):
    job = {
        "schema_version": "1.0",
        "job_id": "ROLLUP-TEST-001",
        "module_id": "boiling",
        "phase": phase,
        "run_mode": "single",
        "input_files": [str(sample)],
        "output_dir": str(output),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    job.update(extra)
    return job


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_job(job, path):
    write_json(path, job)
    assert boiling_module.run_job(path) == 0
    return json.loads(
        (Path(job["output_dir"]) / "result.json").read_text(encoding="utf-8")
    )


def finalized_snapshot(tmp_path):
    sample = tmp_path / "month.xlsx"
    make_sample(sample)
    draft_output = tmp_path / "draft"
    draft = run_job(
        make_job(sample, draft_output),
        tmp_path / "draft-job.json",
    )
    conclusion_confirmation = next(
        item
        for item in draft["confirmations"]
        if item["confirmation_id"].startswith("C-CONCLUSION-RULE-")
    )
    ai_request = next(
        item for item in draft["service_requests"] if item["service"] == "ai"
    )
    confirmation_file = tmp_path / "confirmations.json"
    write_json(
        confirmation_file,
        {
            "schema_version": "1.0",
            "task_id": draft["job_id"],
            "module_id": "boiling",
            "answers": [
                {
                    "confirmation_id": conclusion_confirmation["confirmation_id"],
                    "value": conclusion_confirmation["suggested_value"],
                    "apply_to_batch": False,
                }
            ],
        },
    )
    ai_items = []
    for candidate in ai_request["payload"]["candidates"]:
        ai_items.append(
            {
                "candidate_id": candidate["candidate_id"],
                "risk_summary": "按月度证据复核。",
                "possible_causes": ["需要核对工艺记录。"],
                "check_items": ["核对对应试件记录。"],
                "retest_recommendations": ["必要时复测。"],
                "priority": "medium",
                "evidence_refs": candidate["evidence_refs"],
            }
        )
    service_file = tmp_path / "service.json"
    write_json(
        service_file,
        {
            "schema_version": "1.0",
            "task_id": draft["job_id"],
            "module_id": "boiling",
            "responses": [
                {
                    "request_id": ai_request["request_id"],
                    "service": "ai",
                    "status": "ok",
                    "text": json.dumps(
                        {
                            "schema_version": "1.0",
                            "overall_summary": "既有 AI 月度建议。",
                            "items": ai_items,
                            "limitations": ["不改变确定性业务输出。"],
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        },
    )
    final_output = tmp_path / "final"
    final = run_job(
        make_job(
            sample,
            final_output,
            phase="finalize",
            job_id="ROLLUP-FINAL-001",
            parent_job_id=draft["job_id"],
            confirmation_file=str(confirmation_file),
            service_response_file=str(service_file),
        ),
        tmp_path / "final-job.json",
    )
    snapshot_path = next(
        Path(item["path"])
        for item in final["outputs"]
        if item["type"] == "monthly_snapshot"
    )
    return final, snapshot_path


def snapshot_variant(snapshot_path, target, *, month, batch_no, year=2026):
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    snapshot["year"] = year
    snapshot["month"] = month
    snapshot["payload"]["records"][0]["test_date"] = f"{year:04d}-{month:02d}-16"
    snapshot["payload"]["records"][0]["batch_no"] = batch_no
    snapshot["payload"]["records"][0]["crack_inspection_confirmed"] = True
    snapshot["payload"]["records"][0]["crack_inspection_status"] = (
        "已检查且符合对应等级"
    )
    write_json(target, snapshot)
    return {
        "month": month,
        "path": str(Path(target).resolve()),
        "sha256": digest(target),
    }


def rollup_request(root, output, *, snapshots, candidate, year=2026, target_month=3):
    return {
        "schema_version": "1.0",
        "request_id": "ROLLUP-REQUEST-001",
        "module_id": "boiling",
        "year": year,
        "target_month": target_month,
        "snapshot_root": str(Path(root).resolve()),
        "output_dir": str(Path(output).resolve()),
        "snapshots": snapshots,
        "candidate_snapshot": candidate,
        "config_identity": {
            "rule_version": boiling_module.load_rules()["rule_version"],
            "sha256": digest(boiling_module.DEFAULT_RULES_FILE),
        },
        "forbid_network": True,
    }


def test_finalize_writes_confirmed_monthly_snapshot_with_existing_ai(tmp_path):
    final, snapshot_path = finalized_snapshot(tmp_path)
    assert final["status"] == "success"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["module_version"] == "1.3.0"
    assert (snapshot["year"], snapshot["month"]) == (2026, 1)
    record = snapshot["payload"]["records"][0]
    assert record["final_confirmation_decisions"][0]["value"] == "不合格"
    assert snapshot["payload"]["ai_review"]["status"] == "ok"
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert not re.search(r"(?i)[a-z]:[\\/]", serialized)


def test_snapshot_uses_final_human_density_and_expansion_values(tmp_path):
    sample = tmp_path / "conflicts.xlsx"
    make_sample(sample)
    workbook = openpyxl.load_workbook(sample)
    try:
        sheet = workbook["水煮实验"]
        sheet.cell(14, 6, 1.2)
        sheet.cell(14, 8, 0.06)
        workbook.save(sample)
    finally:
        workbook.close()
    draft_output = tmp_path / "draft-conflicts"
    draft = run_job(
        make_job(sample, draft_output),
        tmp_path / "draft-conflicts-job.json",
    )
    conflict_prompts = [
        item
        for item in draft["confirmations"]
        if item["confirmation_id"].startswith("C-CONFLICT-")
    ]
    assert len(conflict_prompts) == 2
    confirmation_file = tmp_path / "conflict-confirmations.json"
    answers = []
    for prompt in conflict_prompts:
        answers.append(
            {
                "confirmation_id": prompt["confirmation_id"],
                "value": prompt["options"][0],
                "apply_to_batch": False,
            }
        )
    write_json(
        confirmation_file,
        {
            "schema_version": "1.0",
            "task_id": draft["job_id"],
            "module_id": "boiling",
            "answers": answers,
        },
    )
    final_output = tmp_path / "final-conflicts"
    final = run_job(
        make_job(
            sample,
            final_output,
            phase="finalize",
            job_id="ROLLUP-FINAL-VALUES",
            parent_job_id=draft["job_id"],
            confirmation_file=str(confirmation_file),
        ),
        tmp_path / "final-conflicts-job.json",
    )
    snapshot_path = next(
        Path(item["path"])
        for item in final["outputs"]
        if item["type"] == "monthly_snapshot"
    )
    record = json.loads(snapshot_path.read_text(encoding="utf-8"))["payload"][
        "records"
    ][0]
    assert record["samples"][0]["density_g_cm3"] == pytest.approx(1.2)
    assert record["samples"][0]["expansion_ratio"] == pytest.approx(0.06)
    assert record["average_density_g_cm3"] == pytest.approx(1.2)
    assert record["average_expansion_ratio"] == pytest.approx(0.06)
    assert {
        item["choice"] for item in record["confirmed_calculation_values"]
    } == {"source"}


def test_finalize_with_unanswered_business_confirmation_has_no_snapshot(tmp_path):
    sample = tmp_path / "unanswered.xlsx"
    make_sample(sample)
    draft_output = tmp_path / "draft-unanswered"
    draft = run_job(
        make_job(sample, draft_output),
        tmp_path / "draft-unanswered-job.json",
    )
    assert draft["confirmations"]
    confirmation_file = tmp_path / "empty-confirmations.json"
    write_json(
        confirmation_file,
        {
            "schema_version": "1.0",
            "task_id": draft["job_id"],
            "module_id": "boiling",
            "answers": [],
        },
    )
    final_output = tmp_path / "final-unanswered"
    final = run_job(
        make_job(
            sample,
            final_output,
            phase="finalize",
            job_id="ROLLUP-FINAL-NO-SNAPSHOT",
            parent_job_id=draft["job_id"],
            confirmation_file=str(confirmation_file),
        ),
        tmp_path / "final-unanswered-job.json",
    )
    assert all(item["type"] != "monthly_snapshot" for item in final["outputs"])
    assert not (final_output / "boiling_monthly_snapshot.json").exists()


def test_rollup_allows_month_gap_and_never_builds_ai_request(tmp_path, monkeypatch):
    _, source_snapshot = finalized_snapshot(tmp_path)
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir()
    january = snapshot_variant(
        source_snapshot,
        snapshot_root / "01.json",
        month=1,
        batch_no="JAN-NEW",
    )
    march = snapshot_variant(
        source_snapshot,
        snapshot_root / "03.json",
        month=3,
        batch_no="MAR-NEW",
    )
    output = tmp_path / "rollup"
    request = rollup_request(
        snapshot_root,
        output,
        snapshots=[january],
        candidate=march,
    )
    request_path = tmp_path / "rollup-request.json"
    response_path = output / "rollup-response.json"
    write_json(request_path, request)
    monkeypatch.setattr(
        boiling_module,
        "build_ai_service_request",
        lambda *_args, **_kwargs: pytest.fail("累计重算不得构造 AI 请求"),
    )

    assert boiling_module.run_monthly_rollup(request_path, response_path) == 0
    response = json.loads(response_path.read_text(encoding="utf-8"))
    expected = json.loads(
        (
            MODULE_ROOT
            / "samples"
            / "expected"
            / "monthly_rollup_gap.expected.json"
        ).read_text(encoding="utf-8")
    )
    assert response["status"] == expected["expected_status"]
    assert response["used_months"] == expected["expected_used_months"]
    assert response["network_call_count"] == expected["expected_network_call_count"]
    assert [item["type"] for item in response["outputs"]] == expected[
        "expected_output_types"
    ]
    request_schema = json.loads(
        (MODULE_ROOT / "schemas" / "monthly-rollup-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    response_schema = json.loads(
        (MODULE_ROOT / "schemas" / "monthly-rollup-response.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(request_schema).validate(request)
    jsonschema.Draft202012Validator(response_schema).validate(response)
    workbook = openpyxl.load_workbook(output / "boiling_summary.xlsx", data_only=True)
    try:
        assert (
            workbook["水煮检测汇总"].max_row - 1
            == expected["expected_record_count"]
        )
        assert workbook["多月趋势"].max_row == 3
    finally:
        workbook.close()
    report = (output / "boiling_analysis.md").read_text(encoding="utf-8")
    assert "既有 AI 月度建议" in report
    assert "网络调用次数为 0" in report


def test_early_month_candidate_replaces_existing_snapshot(tmp_path):
    _, source_snapshot = finalized_snapshot(tmp_path)
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir()
    january_old = snapshot_variant(
        source_snapshot,
        snapshot_root / "01-old.json",
        month=1,
        batch_no="JAN-OLD",
    )
    january_new = snapshot_variant(
        source_snapshot,
        snapshot_root / "01-new.json",
        month=1,
        batch_no="JAN-REPLACED",
    )
    march = snapshot_variant(
        source_snapshot,
        snapshot_root / "03.json",
        month=3,
        batch_no="MAR-KEEP",
    )
    output = tmp_path / "rollup"
    request = rollup_request(
        snapshot_root,
        output,
        snapshots=[january_old, march],
        candidate=january_new,
    )
    request_path = tmp_path / "request.json"
    response_path = output / "response.json"
    write_json(request_path, request)

    assert boiling_module.run_monthly_rollup(request_path, response_path) == 0
    records = json.loads(
        (output / "boiling_records.json").read_text(encoding="utf-8")
    )["records"]
    assert [record["batch_no"] for record in records] == ["JAN-REPLACED", "MAR-KEEP"]
    assert all(record["crack_inspection_confirmed"] is True for record in records)
    assert all(
        record["crack_inspection_status"] == "已检查且符合对应等级"
        for record in records
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("out_of_order", "月份乱序"),
        ("duplicate", "重复月份"),
        ("hash", "哈希不一致"),
        ("cross_year", "年份与累计请求不一致"),
    ],
)
def test_rollup_rejects_order_duplicate_hash_and_cross_year(
    tmp_path,
    mutation,
    message,
):
    _, source_snapshot = finalized_snapshot(tmp_path)
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir()
    january = snapshot_variant(
        source_snapshot,
        snapshot_root / "01.json",
        month=1,
        batch_no="JAN",
    )
    february = snapshot_variant(
        source_snapshot,
        snapshot_root / "02.json",
        month=2,
        batch_no="FEB",
    )
    march = snapshot_variant(
        source_snapshot,
        snapshot_root / "03.json",
        month=3,
        batch_no="MAR",
    )
    snapshots = [january, february]
    candidate = march
    if mutation == "out_of_order":
        snapshots = [february, january]
    elif mutation == "duplicate":
        snapshots = [january, copy.deepcopy(january)]
    elif mutation == "hash":
        snapshots[0] = {**january, "sha256": "0" * 64}
    elif mutation == "cross_year":
        january = snapshot_variant(
            source_snapshot,
            snapshot_root / "01-cross-year.json",
            month=1,
            batch_no="JAN",
            year=2025,
        )
        snapshots = [january]
    output = tmp_path / "rollup"
    request = rollup_request(
        snapshot_root,
        output,
        snapshots=snapshots,
        candidate=candidate,
    )
    request_path = tmp_path / "request.json"
    response_path = output / "response.json"
    write_json(request_path, request)

    assert boiling_module.run_monthly_rollup(request_path, response_path) == 2
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["status"] == "failed"
    assert message in response["error"]
    assert response["network_call_count"] == 0


def test_module_owned_schemas_validate_examples(tmp_path):
    _, snapshot_path = finalized_snapshot(tmp_path)
    schema_dir = MODULE_ROOT / "schemas"
    snapshot_schema = json.loads(
        (schema_dir / "monthly-snapshot.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(snapshot_schema).validate(
        json.loads(snapshot_path.read_text(encoding="utf-8"))
    )
    learning_schema = json.loads(
        (schema_dir / "confirmation-learning.schema.json").read_text(encoding="utf-8")
    )
    description = boiling_module.learning_description_for_confirmation(
        {"confirmation_id": "C-EXPANSION-REVIEW-0123456789ab"},
        {"product_usage": "墙板"},
    )
    assert description is not None
    learning_payload = {
        "schema_version": "1.0",
        "module_id": "boiling",
        "descriptions": [description],
    }
    jsonschema.Draft202012Validator(learning_schema).validate(learning_payload)
    serialized = json.dumps(learning_payload, ensure_ascii=False)
    assert "脱敏竹材" not in serialized
    assert not re.search(r"(?i)[a-z]:[\\/]", serialized)


def test_source_and_optional_portable_rollup_entrypoints(tmp_path):
    _, source_snapshot = finalized_snapshot(tmp_path)
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir()
    candidate = snapshot_variant(
        source_snapshot,
        snapshot_root / "01.json",
        month=1,
        batch_no="SOURCE-CLI",
    )
    output = tmp_path / "source-output"
    request = rollup_request(
        snapshot_root,
        output,
        snapshots=[],
        candidate=candidate,
        target_month=1,
    )
    request_path = tmp_path / "request.json"
    response_path = output / "response.json"
    write_json(request_path, request)
    environment = os.environ.copy()
    environment["BAMBOO_PYTHON"] = sys.executable
    source_result = subprocess.run(
        [
            str(MODULE_ROOT / "run_module.bat"),
            "rollup",
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=MODULE_ROOT.parents[1],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert source_result.returncode == 0, source_result.stderr
    assert json.loads(response_path.read_text(encoding="utf-8"))["status"] == "success"

    portable = os.environ.get("BOILING_PORTABLE_RUNTIME")
    if not portable:
        pytest.skip("设置 BOILING_PORTABLE_RUNTIME 后复验便携入口")
    portable_output = tmp_path / "portable-output"
    portable_request = copy.deepcopy(request)
    portable_request["output_dir"] = str(portable_output.resolve())
    portable_request_path = tmp_path / "portable-request.json"
    portable_response_path = portable_output / "response.json"
    write_json(portable_request_path, portable_request)
    portable_result = subprocess.run(
        [
            portable,
            "rollup",
            "--request",
            str(portable_request_path),
            "--response",
            str(portable_response_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert portable_result.returncode == 0, portable_result.stderr
    assert (
        json.loads(portable_response_path.read_text(encoding="utf-8"))["status"]
        == "success"
    )

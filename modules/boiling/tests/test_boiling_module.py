import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import openpyxl

MODULE_ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "boiling_module", MODULE_ROOT / "src" / "boiling_module.py"
)
assert MODULE_SPEC and MODULE_SPEC.loader
boiling_module = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(boiling_module)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_sample(path, include_samples=True):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "水煮实验"
    sheet.cell(2, 1, "TEST-001")
    sheet.cell(3, 3, "脱敏竹材")
    sheet.cell(3, 7, "100*100*10")
    sheet.cell(5, 3, dt.date(2026, 7, 16))
    if include_samples:
        sheet.cell(8, 1, "样1")
        sheet.cell(8, 2, 100)
        sheet.cell(8, 3, 100)
        sheet.cell(9, 5, 120)
        for row in range(8, 14):
            sheet.cell(row, 4, 10.0)
            sheet.cell(row, 7, 10.5)
        sheet.cell(14, 6, 1.2)
        sheet.cell(14, 8, 0.05)
        sheet.cell(17, 1, "检测结论：密度检测合格，2h膨胀率检测合格，浸渍剥离检测合格")
        sheet.cell(17, 8, "测试员")
    workbook.save(path)


def make_job(sample, output, phase="draft", **extra):
    job = {
        "schema_version": "1.0",
        "job_id": "TEST-JOB-001",
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


def make_labeled_sample(
    path,
    *,
    sample_count=1,
    density=1.2,
    expansion=0.05,
    product_usage="家具",
    conclusion="密度检测合格，2h膨胀率检测合格，浸渍剥离检测合格",
    include_retest=False,
    source_density=None,
    source_expansion=None,
):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "水煮实验"
    sheet.append(["批号", "DEMO-001", "产品名称", "脱敏竹集成材", "规格型号", "100×100×10"])
    sheet.append(["压制日期", dt.date(2026, 7, 10), "班长", "脱敏班长", "产品用途", product_usage])
    sheet.append(["检测日期", dt.date(2026, 7, 16), "浸胶日期", dt.date(2026, 7, 11), "订单号", "ORDER-DEMO-001"])
    start = 8
    total = sample_count + (1 if include_retest else 0)
    for index in range(total):
        label = "复测1" if include_retest and index == total - 1 else f"样{index + 1}"
        sample_start = start + index * 7
        sheet.cell(sample_start, 1, label)
        sheet.cell(sample_start, 2, 100)
        sheet.cell(sample_start, 3, 100)
        avg_before = 10.0
        avg_after = avg_before * (1 + expansion)
        weight = density * (100 * 100 * avg_before / 1000)
        sheet.cell(sample_start + 1, 5, weight)
        for row in range(sample_start, sample_start + 6):
            sheet.cell(row, 4, avg_before)
            sheet.cell(row, 7, avg_after)
        sheet.cell(sample_start + 6, 6, density if source_density is None else source_density)
        sheet.cell(sample_start + 6, 8, expansion if source_expansion is None else source_expansion)
    conclusion_row = start + total * 7 + 2
    sheet.cell(conclusion_row, 1, f"检测结论：{conclusion}")
    sheet.cell(conclusion_row, 7, "检测员")
    sheet.cell(conclusion_row, 8, "脱敏测试员")
    workbook.save(path)


def load_result(output):
    return json.loads((Path(output) / "result.json").read_text(encoding="utf-8"))


def test_extract_sample(tmp_path):
    sample = tmp_path / "sample.xlsx"
    make_sample(sample)
    record = boiling_module.extract_file(sample)
    assert record["product"] == "脱敏竹材"
    assert len(record["samples"]) == 1
    assert record["average_density_g_cm3"] == 1.2
    assert record["average_expansion_ratio"] == 0.05


def test_draft_job_generates_result_without_modifying_source(tmp_path):
    sample = tmp_path / "sample.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample, product_usage="")
    before = digest(sample)
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    assert before == digest(sample)
    assert (output / "boiling_summary.xlsx").is_file()
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "needs_confirmation"
    assert result["summary"]["processed_count"] == 1
    assert result["confirmations"][0]["field"] == "product_usage"


def test_finalize_applies_confirmation(tmp_path):
    sample = tmp_path / "sample.xlsx"
    draft_output = tmp_path / "draft"
    final_output = tmp_path / "final"
    draft_job_path = tmp_path / "draft-job.json"
    final_job_path = tmp_path / "final-job.json"
    confirmation_path = tmp_path / "confirmation.json"
    make_labeled_sample(sample, product_usage="")
    draft_job_path.write_text(
        json.dumps(make_job(sample, draft_output), ensure_ascii=False), encoding="utf-8"
    )
    assert boiling_module.run_job(draft_job_path) == 0
    draft_result = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    confirmation_id = draft_result["confirmations"][0]["confirmation_id"]
    confirmation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "TEST-JOB-001",
                "answers": [
                    {
                        "confirmation_id": confirmation_id,
                        "value": "家具",
                        "apply_to_batch": False,
                        "remember_mapping": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    final_job = make_job(
        sample,
        final_output,
        phase="finalize",
        parent_job_id="TEST-JOB-001",
        confirmation_file=str(confirmation_path),
    )
    final_job["job_id"] = "TEST-JOB-002"
    final_job_path.write_text(json.dumps(final_job, ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(final_job_path) == 0
    result = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["confirmations"] == []


def test_bad_workbook_is_structured_failure(tmp_path):
    sample = tmp_path / "broken.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    sample.write_bytes(b"not-an-excel-file")
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 3
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["summary"]["failed_count"] == 1


def test_invalid_job_returns_two(tmp_path):
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps({"module_id": "moisture"}), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 2


def test_empty_sheet_does_not_enter_normal_summary(tmp_path):
    sample = tmp_path / "empty.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_sample(sample, include_samples=False)
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "needs_confirmation"
    assert result["summary"]["processed_count"] == 0
    assert (output / "boiling_summary.xlsx").is_file()


def test_extracts_all_handoff_fields_and_recalculates(tmp_path):
    sample = tmp_path / "labeled.xlsx"
    make_labeled_sample(sample)
    record = boiling_module.extract_file(sample)
    assert record["batch_no"] == "DEMO-001"
    assert record["product"] == "脱敏竹集成材"
    assert record["specification"] == "100×100×10"
    assert record["pressing_date"] == "2026-07-10"
    assert record["team_leader"] == "脱敏班长"
    assert record["test_date"] == "2026-07-16"
    assert record["impregnation_date"] == "2026-07-11"
    assert record["order_info"] == "ORDER-DEMO-001"
    assert record["product_usage"] == "家具"
    assert record["samples"][0]["volume_cm3"] == 100
    assert record["samples"][0]["calculated_density_g_cm3"] == 1.2
    assert record["samples"][0]["calculated_expansion_ratio"] == 0.05


def test_variable_sample_count_and_retest_are_preserved(tmp_path):
    sample = tmp_path / "variable.xlsx"
    make_labeled_sample(sample, sample_count=3, include_retest=True)
    record = boiling_module.extract_file(sample)
    assert len(record["samples"]) == 4
    assert [item["sample_type"] for item in record["samples"]].count("retest") == 1


def test_product_usage_in_source_does_not_request_confirmation(tmp_path):
    sample = tmp_path / "usage.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample, product_usage="家具")
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    assert result["status"] == "success"
    assert result["confirmations"] == []
    assert result["service_requests"] == []
    assert {item["type"] for item in result["outputs"]} == {
        "summary_excel",
        "analysis_report",
        "business_records",
    }


def test_density_observation_is_not_presented_as_formal_verdict(tmp_path):
    sample = tmp_path / "density.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample, density=1.45)
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    anomaly = next(item for item in result["anomalies"] if item["field"] == "average_density_g_cm3")
    assert anomaly["severity"] == "warning"
    assert "不能作为正式" in anomaly["message"]
    assert result["status"] == "needs_confirmation"


def test_expansion_observation_uses_product_usage_threshold(tmp_path):
    sample = tmp_path / "expansion.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample, expansion=0.10, product_usage="家具")
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    assert any(item["field"] == "average_expansion_ratio" for item in result["anomalies"])


def test_peel_failure_is_preserved_as_source_anomaly(tmp_path):
    sample = tmp_path / "peel.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample, conclusion="密度检测合格，浸渍剥离检测不合格")
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    assert any(item["field"] == "immersion_peel_result" and item["value"] == "不合格" for item in result["anomalies"])


def test_source_and_recalculated_conflict_are_both_retained(tmp_path):
    sample = tmp_path / "conflict.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample, density=1.2, source_density=1.28, source_expansion=0.08)
    record = boiling_module.extract_file(sample)
    assert len(record["conflicts"]) == 2
    assert record["samples"][0]["source_density_g_cm3"] == 1.28
    assert record["samples"][0]["calculated_density_g_cm3"] == 1.2
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    assert any(item["rule_id"] == "BOILING-CALC-CONFLICT-001" for item in result["anomalies"])
    assert any(item["field"] == "density_g_cm3" for item in result["confirmations"])


def test_batch_mode_isolates_bad_file_and_skips_duplicate(tmp_path):
    sample = tmp_path / "sample.xlsx"
    duplicate = tmp_path / "duplicate.xlsx"
    broken = tmp_path / "broken.xlsx"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample)
    duplicate.write_bytes(sample.read_bytes())
    broken.write_bytes(b"not an xlsx")
    job = make_job(sample, output)
    job["run_mode"] = "batch"
    job["input_files"] = [str(sample), str(duplicate), str(broken)]
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    assert result["summary"]["processed_count"] == 1
    assert result["summary"]["skipped_count"] == 1
    assert result["summary"]["failed_count"] == 1


def test_unsupported_extension_fails_without_output_artifacts(tmp_path):
    sample = tmp_path / "sample.xls"
    output = tmp_path / "output"
    job_path = tmp_path / "job.json"
    sample.write_bytes(b"legacy")
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 3
    result = load_result(output)
    assert result["status"] == "failed"
    assert result["outputs"] == []


def test_invalid_json_returns_two_without_creating_output(tmp_path):
    job_path = tmp_path / "job.json"
    job_path.write_text("{not-json", encoding="utf-8")
    assert boiling_module.run_job(job_path) == 2


def test_ai_disabled_and_enabled_never_calls_external_service(tmp_path):
    sample = tmp_path / "sample.xlsx"
    make_labeled_sample(sample)
    for enabled in (False, True):
        output = tmp_path / f"output-{enabled}"
        job_path = tmp_path / f"job-{enabled}.json"
        job = make_job(sample, output, ai_enabled=enabled)
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        assert boiling_module.run_job(job_path) == 0
        assert load_result(output)["service_requests"] == []


def test_outputs_are_inside_declared_output_directory(tmp_path):
    sample = tmp_path / "sample.xlsx"
    output = tmp_path / "declared-output"
    job_path = tmp_path / "job.json"
    make_labeled_sample(sample)
    job_path.write_text(json.dumps(make_job(sample, output), ensure_ascii=False), encoding="utf-8")
    assert boiling_module.run_job(job_path) == 0
    result = load_result(output)
    declared = output.resolve()
    assert all(Path(item["path"]).resolve().is_relative_to(declared) for item in result["outputs"])


def test_all_sanitized_samples_match_machine_expected_results(tmp_path):
    input_dir = MODULE_ROOT / "tests" / "fixtures" / "samples" / "input"
    expected_dir = MODULE_ROOT / "samples" / "expected"
    samples = sorted(input_dir.glob("*.xlsx"))
    assert len(samples) == 8
    for index, sample in enumerate(samples, 1):
        output = tmp_path / sample.stem
        job_path = tmp_path / f"job-{index}.json"
        job = make_job(sample, output)
        job["job_id"] = f"EXPECTED-{index:03d}"
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        assert boiling_module.run_job(job_path) == 0
        result = load_result(output)
        record = boiling_module.extract_file(sample)
        expected = json.loads(
            (expected_dir / f"{sample.stem}.expected.json").read_text(encoding="utf-8")
        )
        actual = {
            "expected_status": result["status"],
            "expected_processed_count": result["summary"]["processed_count"],
            "expected_failed_count": result["summary"]["failed_count"],
            "expected_anomaly_fields": sorted(item["field"] for item in result["anomalies"]),
            "expected_confirmation_fields": sorted(item["field"] for item in result["confirmations"]),
            "expected_sample_count": len(record["samples"]),
            "expected_retest_count": sum(item["sample_type"] == "retest" for item in record["samples"]),
            "expected_immersion_peel_result": record["immersion_peel_result"],
            "expected_average_density_g_cm3": record["average_density_g_cm3"],
            "expected_average_expansion_ratio": record["average_expansion_ratio"],
            "expected_conflict_count": len(record["conflicts"]),
        }
        for key, value in actual.items():
            assert expected[key] == value, f"{sample.name}: {key}"

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import openpyxl
import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent import MODULE_VERSION  # noqa: E402
from after_sales_agent.manual_review import build_required_review_prompts  # noqa: E402
from after_sales_agent.monthly_rollup import (  # noqa: E402
    MonthlyRollupError,
    build_monthly_snapshot,
    file_sha256,
    render_monthly_rollup,
    run_rollup_request,
    write_finalize_monthly_snapshot,
)

from core.contracts.monthly import MonthlyRollupRequest, MonthlyRollupResult  # noqa: E402
from core.contracts.result import LearningDescriptor  # noqa: E402


def _record(
    *,
    year: int = 2026,
    month: int = 1,
    fee: float = 100.0,
    source_file: str = r"D:\sensitive\客户甲售后申请.xlsx",
    input_index: int = 1,
) -> dict[str, object]:
    return {
        "input_index": input_index,
        "file_sha256": f"{input_index:064x}",
        "source_file": source_file,
        "sheet": "售后单",
        "included_in_summary": True,
        "analysis_status": "智能分析完成",
        "customer": "客户甲",
        "feedback": "客户甲电话 13800000000，反馈原始投诉内容。",
        "application": "原始方案申请内容。",
        "investigation": "原始调查记录。",
        "solution": "原始解决方案。",
        "product": "桃花江竹地板",
        "spec": "1860*139*18",
        "order_no": f"TEST-{year}-{month:02d}-{input_index}",
        "complaint_date": f"{year}-{month:02d}-10",
        "year": year,
        "month": month,
        "brand": "桃花江",
        "issue_types": ["加工"],
        "primary_issue_type": "加工",
        "after_sales_fee_amount": fee,
        "after_sales_fee_status": "已复核",
        "after_sales_fee_reviewed": True,
        "fee_amount": fee,
        "fee_status": "exact",
        "enterprise_cost_amount": fee,
        "enterprise_cost_status": "exact",
        "enterprise_cost_reviewed": True,
        "internal_accountability_amount": 0.0,
        "internal_accountability_status": "exact",
        "internal_accountability_reviewed": True,
        "external_borne_amount": 0.0,
        "external_borne_status": "exact",
        "external_borne_reviewed": True,
        "fee_currency": "CNY",
        "responsible_factory": "二厂",
        "responsibility_reviewed": True,
        "complaint_type_reviewed": True,
        "manual_review_completed": True,
        "mandatory_review_pending": False,
        "needs_review": False,
        "resolution_status": "已解决",
        "case_status": "已关闭",
        "closed": True,
        "reviewed": True,
    }


def _write_snapshot(
    directory: Path,
    *,
    year: int,
    month: int,
    fee: float,
    input_index: int,
) -> tuple[Path, str]:
    path = directory / f"{year}-{month:02d}.json"
    snapshot = build_monthly_snapshot(
        [
            _record(
                year=year,
                month=month,
                fee=fee,
                input_index=input_index,
            )
        ],
        year=year,
        month=month,
    )
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path, file_sha256(path)


def _request(
    *,
    year: int,
    target_month: int,
    snapshots: list[tuple[int, Path, str]],
    output_dir: Path,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "transaction_id": f"rollup-{year}-{target_month:02d}",
        "module_id": "after_sales",
        "module_version": MODULE_VERSION,
        "year": year,
        "target_month": target_month,
        "offline_required": True,
        "snapshots": [
            {
                "snapshot_id": f"snapshot-{year}-{month:02d}",
                "job_id": f"job-{year}-{month:02d}",
                "module_id": "after_sales",
                "year": year,
                "month": month,
                "path": str(path.resolve()),
                "size": path.stat().st_size,
                "sha256": digest,
            }
            for month, path, digest in snapshots
        ],
        "snapshot_root": str(snapshots[0][1].parent.resolve()),
        "output_dir": str(output_dir.resolve()),
        "configuration_identity": {
            "version": "after-sales-default",
            "sha256": "1" * 64,
        },
    }


def test_snapshot_contains_only_final_anonymized_structured_values() -> None:
    snapshot = build_monthly_snapshot([_record()], year=2026, month=1)
    serialized = json.dumps(snapshot, ensure_ascii=False)
    item = snapshot["payload"]["records"][0]

    assert snapshot["snapshot_format"] == "module-owned-v1"
    assert snapshot["module_version"] == MODULE_VERSION
    assert item["after_sales_fee_amount"] == 100.0
    assert item["responsible_factory"] == "二厂"
    assert item["primary_issue_type"] == "加工"
    assert item["source_file"] == "售后记录-0001.xlsx"
    assert "客户甲" not in serialized
    assert "13800000000" not in serialized
    assert r"D:\sensitive" not in serialized
    assert "feedback" not in item
    assert "solution" not in item
    assert "source_cells" not in item


def test_snapshot_rejects_record_without_all_required_human_reviews() -> None:
    record = _record()
    record["responsibility_reviewed"] = False
    record["manual_review_completed"] = False

    with pytest.raises(MonthlyRollupError) as error:
        build_monthly_snapshot([record], year=2026, month=1)

    assert error.value.code == "SNAPSHOT_RECORD_NOT_FINAL"


def test_complaint_type_learning_descriptor_is_stable_and_anonymized() -> None:
    rules = {
        "brand_order": ["桃花江", "竹语堂", "海外"],
        "issue_order": ["性能", "外观", "加工", "其他"],
    }
    first = _record()
    first["product"] = "桃花江户外竹地板"
    first["customer"] = "客户甲"
    first["source_file"] = r"D:\客户资料\客户甲售后申请.xlsx"
    second = deepcopy(first)
    second["customer"] = "客户乙"
    second["source_file"] = r"D:\其他目录\客户乙售后申请.xlsx"

    first_learning = build_required_review_prompts(first, rules)[2]["learning"]
    second_learning = build_required_review_prompts(second, rules)[2]["learning"]
    serialized = json.dumps(first_learning, ensure_ascii=False)

    assert first_learning == second_learning
    assert first_learning["learning_key"] == "after_sales.complaint_type.v1"
    assert first_learning["context"] == {
        "brand_group": "桃花江",
        "product_group": "地板",
    }
    assert first_learning["preference_adjustable"] is True
    assert first_learning["base_suggestion_id"] == "processing"
    assert first_learning["context_levels"] == [
        ["brand_group", "product_group"],
        ["brand_group"],
    ]
    assert [item["candidate_id"] for item in first_learning["candidates"]] == [
        "performance",
        "appearance",
        "processing",
        "other",
    ]
    assert "客户甲" not in serialized
    assert "D:\\" not in serialized
    LearningDescriptor.model_validate(first_learning)


def test_finalize_writes_internal_snapshot_for_single_month(tmp_path: Path) -> None:
    written = write_finalize_monthly_snapshot(
        [
            _record(year=2026, month=4, fee=120.0, input_index=1),
            _record(year=2026, month=4, fee=80.0, input_index=2),
            _record(year=2026, month=3, fee=900.0, input_index=3),
        ],
        tmp_path,
        year=2026,
        month=4,
    )

    assert written is not None
    assert written.name == "after_sales_monthly_snapshot.json"
    conventional = tmp_path / "after_sales_monthly_snapshot.json"
    assert conventional.is_file()
    snapshot = json.loads(conventional.read_text(encoding="utf-8"))
    assert snapshot["payload"]["record_count"] == 2
    assert sum(
        item["after_sales_fee_amount"] for item in snapshot["payload"]["records"]
    ) == 200.0


def test_rollup_allows_month_gap_and_makes_complete_offline_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    january, january_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    march, march_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=3,
        fee=300.0,
        input_index=2,
    )
    output_dir = tmp_path / "staging"

    def blocked_network(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"累计渲染不得访问网络：{args!r} {kwargs!r}")

    monkeypatch.setattr(socket, "create_connection", blocked_network)
    response = render_monthly_rollup(
        _request(
            year=2026,
            target_month=3,
            snapshots=[
                (1, january, january_hash),
                (3, march, march_hash),
            ],
            output_dir=output_dir,
        )
    )
    MonthlyRollupRequest.model_validate(
        _request(
            year=2026,
            target_month=3,
            snapshots=[
                (1, january, january_hash),
                (3, march, march_hash),
            ],
            output_dir=output_dir,
        )
    )
    MonthlyRollupResult.model_validate(response)

    assert response["status"] == "success"
    assert response["used_months"] == [1, 3]
    assert response["network_call_count"] == 0
    assert response["record_count"] == 2
    assert response["error"] is None
    assert len(response["outputs"]) == 7
    assert all(Path(item["path"]).is_file() for item in response["outputs"])
    assert all(
        file_sha256(Path(item["path"])) == item["sha256"]
        for item in response["outputs"]
    )
    records = json.loads((output_dir / "after_sales_records.json").read_text("utf-8"))
    assert [item["month"] for item in records["records"]] == [1, 3]
    assert sum(item["after_sales_fee_amount"] for item in records["records"]) == 400.0
    rollup_source = (
        MODULE_ROOT / "src" / "after_sales_agent" / "monthly_rollup.py"
    ).read_text(encoding="utf-8")
    assert "ai_service" not in rollup_source


def test_early_month_replacement_recalculates_later_cumulative_result(
    tmp_path: Path,
) -> None:
    january, january_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    march, march_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=3,
        fee=300.0,
        input_index=2,
    )
    first_dir = tmp_path / "first"
    render_monthly_rollup(
        _request(
            year=2026,
            target_month=3,
            snapshots=[
                (1, january, january_hash),
                (3, march, march_hash),
            ],
            output_dir=first_dir,
        )
    )

    replacement, replacement_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=500.0,
        input_index=3,
    )
    second_dir = tmp_path / "replacement"
    render_monthly_rollup(
        _request(
            year=2026,
            target_month=3,
            snapshots=[
                (1, replacement, replacement_hash),
                (3, march, march_hash),
            ],
            output_dir=second_dir,
        )
    )

    first = json.loads((first_dir / "after_sales_records.json").read_text("utf-8"))
    second = json.loads((second_dir / "after_sales_records.json").read_text("utf-8"))
    assert sum(item["after_sales_fee_amount"] for item in first["records"]) == 400.0
    assert sum(item["after_sales_fee_amount"] for item in second["records"]) == 800.0
    workbook = openpyxl.load_workbook(second_dir / "after_sales_monthly_fee.xlsx")
    assert "年度月度费用" in workbook.sheetnames


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda request: request["snapshots"].reverse(),
            "ROLLUP_SNAPSHOT_ORDER_INVALID",
        ),
        (
            lambda request: request["snapshots"].append(
                deepcopy(request["snapshots"][0])
            ),
            "ROLLUP_SNAPSHOT_MONTH_DUPLICATE",
        ),
        (
            lambda request: request["snapshots"][0].update({"sha256": "0" * 64}),
            "ROLLUP_SNAPSHOT_HASH_MISMATCH",
        ),
    ],
)
def test_rollup_rejects_disorder_duplicate_and_hash_damage(
    tmp_path: Path,
    mutator,
    expected_code: str,
) -> None:
    january, january_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    march, march_hash = _write_snapshot(
        tmp_path,
        year=2026,
        month=3,
        fee=300.0,
        input_index=2,
    )
    request = _request(
        year=2026,
        target_month=3,
        snapshots=[
            (1, january, january_hash),
            (3, march, march_hash),
        ],
        output_dir=tmp_path / expected_code,
    )
    mutator(request)

    with pytest.raises(MonthlyRollupError) as error:
        render_monthly_rollup(request)

    assert error.value.code == expected_code


def test_rollup_rejects_cross_year_snapshot(tmp_path: Path) -> None:
    snapshot, digest = _write_snapshot(
        tmp_path,
        year=2025,
        month=12,
        fee=100.0,
        input_index=1,
    )
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, digest)],
        output_dir=tmp_path / "cross-year",
    )

    with pytest.raises(MonthlyRollupError) as error:
        render_monthly_rollup(request)

    assert error.value.code == "ROLLUP_SNAPSHOT_YEAR_MISMATCH"


def test_rollup_rejects_snapshot_size_mismatch(tmp_path: Path) -> None:
    snapshot, digest = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, digest)],
        output_dir=tmp_path / "size-mismatch",
    )
    request["snapshots"][0]["size"] += 1

    with pytest.raises(MonthlyRollupError) as error:
        render_monthly_rollup(request)

    assert error.value.code == "ROLLUP_SNAPSHOT_SIZE_MISMATCH"


def test_rollup_rejects_snapshot_outside_authorized_root(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir()
    snapshot, digest = _write_snapshot(
        snapshot_root,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, digest)],
        output_dir=tmp_path / "outside-root",
    )
    other_root = tmp_path / "other-root"
    other_root.mkdir()
    request["snapshot_root"] = str(other_root.resolve())

    with pytest.raises(MonthlyRollupError) as error:
        render_monthly_rollup(request)

    assert error.value.code == "ROLLUP_SNAPSHOT_PATH_OUTSIDE_ROOT"


def test_rollup_rejects_snapshot_link_or_reparse_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, digest = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, digest)],
        output_dir=tmp_path / "link-rejected",
    )
    original_is_symlink = Path.is_symlink

    def mark_snapshot_as_link(path: Path) -> bool:
        return path == snapshot or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", mark_snapshot_as_link)

    with pytest.raises(MonthlyRollupError) as error:
        render_monthly_rollup(request)

    assert error.value.code == "ROLLUP_SNAPSHOT_PATH_INVALID"


def test_rollup_rejects_staging_link_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, digest = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    staging = tmp_path / "linked-staging"
    staging.mkdir()
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, digest)],
        output_dir=staging,
    )
    original_is_symlink = Path.is_symlink

    def mark_staging_as_link(path: Path) -> bool:
        return path == staging or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", mark_staging_as_link)

    with pytest.raises(MonthlyRollupError) as error:
        render_monthly_rollup(request)

    assert error.value.code == "ROLLUP_STAGING_REPARSE_POINT"
    assert not (staging / "after_sales_master_summary.xlsx").exists()


def test_rollup_cli_writes_stable_error_response_without_traceback(
    tmp_path: Path,
) -> None:
    snapshot, digest = _write_snapshot(
        tmp_path,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, "0" * 64)],
        output_dir=tmp_path / "output",
    )
    request_path = tmp_path / "request.json"
    response_path = tmp_path / "response.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

    assert run_rollup_request(request_path.resolve(), response_path.resolve()) == 2
    response = json.loads(response_path.read_text(encoding="utf-8"))
    MonthlyRollupResult.model_validate(response)
    assert response["status"] == "failed"
    assert response["error"]["code"] == "rollup_snapshot_hash_mismatch"
    assert "traceback" not in json.dumps(response, ensure_ascii=False).casefold()
    assert digest != "0" * 64


@pytest.mark.skipif(
    not os.environ.get("PORTABLE_AFTER_SALES_ROOT"),
    reason="需要显式提供已构建的售后便携模块目录",
)
def test_portable_runtime_accepts_central_rollup_contract(tmp_path: Path) -> None:
    portable_root = Path(os.environ["PORTABLE_AFTER_SALES_ROOT"]).resolve()
    snapshot_root = tmp_path / "snapshot-root"
    snapshot_root.mkdir()
    snapshot, digest = _write_snapshot(
        snapshot_root,
        year=2026,
        month=1,
        fee=100.0,
        input_index=1,
    )
    output_dir = tmp_path / "portable-output"
    request = _request(
        year=2026,
        target_month=1,
        snapshots=[(1, snapshot, digest)],
        output_dir=output_dir,
    )
    request_path = tmp_path / "portable-request.json"
    response_path = output_dir / "rollup-result.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            str(portable_root / "run_module.bat"),
            "rollup",
            "--request",
            str(request_path.resolve()),
            "--response",
            str(response_path.resolve()),
        ],
        cwd=portable_root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    response = json.loads(response_path.read_text(encoding="utf-8"))
    MonthlyRollupResult.model_validate(response)
    assert response["transaction_id"] == request["transaction_id"]
    assert response["network_call_count"] == 0
    assert all(Path(item["path"]).is_file() for item in response["outputs"])

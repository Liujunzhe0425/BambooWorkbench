from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_demo_covers_three_modules_confirmation_and_offline_boundary() -> None:
    script = (ROOT / "docs/demo/customer-demo-script.md").read_text(encoding="utf-8")
    for phrase in ("竹丝水分", "水煮实验", "售后分析", "待确认", "模拟AI", "拒绝联网", "结果目录"):
        assert phrase in script


def test_customer_record_is_blank_and_has_explicit_decisions() -> None:
    record = (ROOT / "docs/demo/customer-acceptance-record.md").read_text(encoding="utf-8")
    for phrase in ("可试用", "修改后复验", "暂不可用", "本模板不预填"):
        assert phrase in record


def test_release_gate_requires_security_packaging_and_user_approval() -> None:
    checklist = (ROOT / "docs/release/release-checklist.md").read_text(encoding="utf-8")
    for phrase in (
        "verify_repo.ps1",
        "verify_installer.ps1",
        "SHA-256",
        "企业真实数据",
        "用户明确批准",
    ):
        assert phrase in checklist


def test_framework_acceptance_report_records_scope_and_verification() -> None:
    report = (
        ROOT / "docs/release/framework-acceptance-report-v0.1.0.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "305 passed, 8 skipped",
        "安装包",
        "SHA-256",
        "空框架",
        "不代表三类真实业务模块",
        "没有进行任何远程推送",
    ):
        assert phrase in report

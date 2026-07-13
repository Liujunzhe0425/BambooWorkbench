from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_handoff_guide_references_executable_contract_assets() -> None:
    guide = (ROOT / "docs/handoff/module-development-guide.md").read_text(encoding="utf-8")
    required = [
        "contracts/schemas/module-manifest.schema.json",
        "contracts/examples/job.json",
        "mock_modules/moisture",
        "python -m app.tools.module_contract_cli validate",
        "phase=finalize",
        "service_response_file",
        "BambooWorkbench",
    ]
    for item in required:
        assert item in guide


def test_handoff_contract_links_exist() -> None:
    for path in (
        ROOT / "contracts/schemas/module-manifest.schema.json",
        ROOT / "contracts/examples/job.json",
        ROOT / "contracts/examples/result.json",
        ROOT / "docs/handoff/module-acceptance-checklist.md",
        ROOT / "docs/handoff/github-workflow.md",
        ROOT / "docs/handoff/三个业务模块最终交接说明.md",
        ROOT / "docs/handoff/GitHub私有仓库建仓与上传教程.md",
    ):
        assert path.is_file()


def test_acceptance_separates_framework_business_and_customer_decisions() -> None:
    checklist = (ROOT / "docs/handoff/module-acceptance-checklist.md").read_text(
        encoding="utf-8"
    )
    for phrase in ("业务正确性", "框架接入", "故障隔离", "联合回归", "尚未进行"):
        assert phrase in checklist


def test_github_workflow_maps_all_module_branches() -> None:
    guide = (ROOT / "docs/handoff/github-workflow.md").read_text(encoding="utf-8")
    for phrase in (
        "module/moisture",
        "module/boiling",
        "module/after-sales",
        "modules/after_sales/",
        "绝不直接合并到 `main`",
    ):
        assert phrase in guide


def test_final_teammate_handoff_is_complete_and_contract_accurate() -> None:
    guide = (ROOT / "docs/handoff/三个业务模块最终交接说明.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "module/moisture",
        "module/boiling",
        "module/after-sales",
        "contracts/schemas/job-request.schema.json",
        "draft",
        "finalize",
        "service_requests",
        "SHA-256",
        "100%",
        "待客户确认",
    ):
        assert phrase in guide
    assert "不要添加 `healthcheck_command`" in guide


def test_github_tutorial_covers_private_manual_upload_and_plan_limits() -> None:
    guide = (ROOT / "docs/handoff/GitHub私有仓库建仓与上传教程.md").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "Private",
        "git remote add origin",
        "git push -u origin main",
        "module/moisture",
        "Add people",
        "GitHub Pro",
        "CODEOWNERS",
        "quality",
    ):
        assert phrase in guide

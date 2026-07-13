from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_quality_workflow_runs_windows_repository_gate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
    )
    assert workflow["jobs"]["quality"]["runs-on"] == "windows-latest"
    run_steps = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["quality"]["steps"]
    )
    assert "scripts/verify_repo.ps1" in run_steps
    assert workflow["permissions"] == {"contents": "read"}


def test_package_workflow_is_manual_or_tag_only() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/package.yml").read_text(encoding="utf-8")
    )
    triggers = workflow["on"]
    assert "workflow_dispatch" in triggers
    assert triggers["push"]["tags"] == ["v*"]
    assert workflow["jobs"]["portable"]["runs-on"] == "windows-latest"


def test_pull_request_template_requires_security_and_rollback_evidence() -> None:
    template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
    for phrase in ("模块合同", "企业真实数据", "API密钥", "回滚说明", "截图"):
        assert phrase in template

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
    assert workflow["jobs"]["quality"]["env"]["PYTHONUTF8"] == "1"


def test_package_workflow_is_manual_or_tag_only() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/package.yml").read_text(encoding="utf-8")
    )
    triggers = workflow["on"]
    assert "workflow_dispatch" in triggers
    assert triggers["push"]["tags"] == ["v*"]
    release_job = workflow["jobs"]["windows_release"]
    assert release_job["runs-on"] == "windows-latest"
    run_steps = "\n".join(step.get("run", "") for step in release_job["steps"])
    for command in (
        "scripts/verify_repo.ps1",
        "scripts/build_installer.ps1",
        "scripts/verify_installer.ps1",
        "scripts/prepare_release.ps1",
    ):
        assert command in run_steps


def test_workflows_pin_only_github_owned_actions() -> None:
    for workflow_name in ("quality.yml", "package.yml"):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
        )
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                action = step.get("uses")
                if action is None:
                    continue
                owner_and_name, revision = action.split("@", maxsplit=1)
                assert owner_and_name.startswith("actions/")
                assert len(revision) == 40
                assert all(character in "0123456789abcdef" for character in revision)


def test_dependabot_and_private_project_policy_files_exist() -> None:
    dependabot = yaml.safe_load(
        (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    )
    assert {update["package-ecosystem"] for update in dependabot["updates"]} == {
        "pip",
        "github-actions",
    }
    assert all(update["target-branch"] == "integration" for update in dependabot["updates"])
    assert all(
        update["ignore"][0]["update-types"] == ["version-update:semver-major"]
        for update in dependabot["updates"]
    )
    for path in (
        "SECURITY.md",
        "CONTRIBUTING.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/module_integration.yml",
    ):
        assert (ROOT / path).is_file()


def test_pull_request_template_requires_security_and_rollback_evidence() -> None:
    template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
    for phrase in ("模块合同", "企业真实数据", "API密钥", "回滚说明", "截图"):
        assert phrase in template

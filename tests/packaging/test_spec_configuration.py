from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spec_bundles_framework_resources_and_both_executables() -> None:
    spec = (ROOT / "packaging/BambooWorkbench.spec").read_text(encoding="utf-8")
    for path in ("contracts", "assets", "logo", "resources", "mock_modules"):
        assert path in spec
    assert '(str(ROOT / "modules"), "modules")' in spec
    assert 'name="BambooWorkbench"' in spec
    assert 'name="BambooModuleHost"' in spec
    assert "console=False" in spec
    assert "APP_ICON" in spec
    assert 'icon=APP_ICON' in spec
    assert "contents_directory=\".\"" in spec


def test_portable_verifier_requires_contracts_brand_and_mock_modules() -> None:
    verifier = (ROOT / "scripts/verify_portable.ps1").read_text(encoding="utf-8")
    for path in (
        "BambooWorkbench.exe",
        "BambooModuleHost.exe",
        "module-manifest.schema.json",
        "team-logo.svg",
        "logo\\team-logo.png",
        "logo\\BambooWorkbench.ico",
        "bamboo.qss",
        "mock_modules\\moisture",
        "mock_modules\\boiling",
        "mock_modules\\after_sales",
    ):
        assert path in verifier


def test_portable_build_requires_and_invokes_real_module_runtime_hooks() -> None:
    builder = (ROOT / "scripts/build_portable.ps1").read_text(encoding="utf-8")
    runtime_builder = (ROOT / "scripts/build_real_module_runtimes.ps1").read_text(
        encoding="utf-8"
    )

    assert "build_real_module_runtimes.ps1" in builder
    assert "build_portable_runtime.ps1" in runtime_builder
    assert "has no build_portable_runtime.ps1 hook" in runtime_builder


def test_portable_verifier_runs_real_modules_without_development_python() -> None:
    verifier = (ROOT / "scripts/verify_portable.ps1").read_text(encoding="utf-8")

    assert "StartInfo.EnvironmentVariables.Clear()" in verifier
    assert "@('version', 'self-check')" in verifier
    assert "ModuleData.module_version" in verifier
    assert "--demo-smoke-test" in verifier

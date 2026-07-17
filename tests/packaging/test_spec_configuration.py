from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spec_bundles_framework_resources_and_all_executables() -> None:
    spec = (ROOT / "packaging/BambooWorkbench.spec").read_text(encoding="utf-8")
    for path in ("contracts", "assets", "logo", "resources", "mock_modules"):
        assert path in spec
    assert 'name="BambooWorkbench"' in spec
    assert 'name="BambooModuleHost"' in spec
    assert 'name="BambooMoistureModule"' in spec
    assert '"modules/moisture"' in spec
    assert "console=False" in spec
    assert "APP_ICON" in spec
    assert 'icon=APP_ICON' in spec
    assert "contents_directory=\".\"" in spec


def test_portable_verifier_requires_contracts_mock_and_real_modules() -> None:
    verifier = (ROOT / "scripts/verify_portable.ps1").read_text(encoding="utf-8")
    for path in (
        "BambooWorkbench.exe",
        "BambooModuleHost.exe",
        "BambooMoistureModule.exe",
        "module-manifest.schema.json",
        "team-logo.svg",
        "logo\\team-logo.png",
        "logo\\BambooWorkbench.ico",
        "bamboo.qss",
        "mock_modules\\moisture",
        "mock_modules\\boiling",
        "mock_modules\\after_sales",
        "modules\\moisture\\module.json",
        "modules\\moisture\\run_module.bat",
        "--real-smoke-test",
    ):
        assert path in verifier

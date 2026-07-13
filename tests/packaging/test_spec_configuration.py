from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_spec_bundles_framework_resources_and_both_executables() -> None:
    spec = (ROOT / "packaging/BambooWorkbench.spec").read_text(encoding="utf-8")
    for path in ("contracts", "assets", "resources", "mock_modules"):
        assert path in spec
    assert 'name="BambooWorkbench"' in spec
    assert 'name="BambooModuleHost"' in spec
    assert "console=False" in spec
    assert "contents_directory=\".\"" in spec


def test_portable_verifier_requires_contracts_brand_and_mock_modules() -> None:
    verifier = (ROOT / "scripts/verify_portable.ps1").read_text(encoding="utf-8")
    for path in (
        "BambooWorkbench.exe",
        "BambooModuleHost.exe",
        "module-manifest.schema.json",
        "team-logo.svg",
        "bamboo.qss",
        "mock_modules\\moisture",
        "mock_modules\\boiling",
        "mock_modules\\after_sales",
    ):
        assert path in verifier

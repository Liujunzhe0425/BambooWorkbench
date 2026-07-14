from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installer_has_stable_app_id_and_never_deletes_local_data() -> None:
    source = (ROOT / "packaging/BambooWorkbench.iss").read_text(encoding="utf-8")
    assert "AppId={{B4A7CF5E-99C0-4CD9-9A30-B5D574A0F012}" in source
    assert "PrivilegesRequired=lowest" in source
    assert "[UninstallDelete]" not in source
    assert "{localappdata}\\BambooWorkbench" not in source
    assert "{localappdata}\\Programs\\BambooWorkbench" in source
    assert "SetupIconFile=..\\logo\\BambooWorkbench.ico" in source
    assert 'IconFilename: "{app}\\logo\\BambooWorkbench.ico"' in source
    assert "UninstallDisplayIcon={app}\\logo\\BambooWorkbench.ico" in source
    assert "ChangesAssociations=yes" in source


def test_installer_verifier_uses_an_isolated_localappdata_and_sentinel() -> None:
    source = (ROOT / "scripts/verify_installer.ps1").read_text(encoding="utf-8")
    for phrase in ("FakeLocalAppData", "preserve-on-uninstall", "--smoke-test"):
        assert phrase in source

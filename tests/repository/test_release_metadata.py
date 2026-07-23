from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_release_metadata_uses_v101_everywhere() -> None:
    assert __version__ == "1.0.1"
    assert 'version = "1.0.1"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "## [1.0.1]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert '#define MyAppVersion "1.0.1"' in (
        ROOT / "packaging/BambooWorkbench.iss"
    ).read_text(encoding="utf-8")
    for script in ("build_installer.ps1", "prepare_release.ps1", "verify_installer.ps1"):
        assert "1.0.1" in (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "BambooWorkbench-v1.0.1-windows" in (
        ROOT / ".github/workflows/package.yml"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "竹简工作台" in readme
    assert "v1.0.1" in readme
    assert "三个真实业务模块" in readme

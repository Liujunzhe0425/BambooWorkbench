from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_release_metadata_uses_v010_everywhere() -> None:
    assert __version__ == "0.1.0"
    assert 'version = "0.1.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "## [0.1.0]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "竹简工作台" in readme
    assert "空框架版本" in readme
    assert "不包含三类业务的真实" in readme

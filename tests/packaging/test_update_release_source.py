from pathlib import Path

from core.updates.service import DEFAULT_RELEASE_API

ROOT = Path(__file__).parents[2]


def test_default_updater_uses_public_primary_repository() -> None:
    assert DEFAULT_RELEASE_API == (
        "https://api.github.com/repos/Liujunzhe0425/"
        "BambooWorkbench/releases/latest"
    )
    assert DEFAULT_RELEASE_API.endswith("/BambooWorkbench/releases/latest")


def test_public_primary_repository_update_contract_is_documented() -> None:
    document = (ROOT / "docs" / "release" / "automatic-updates.md").read_text(
        encoding="utf-8"
    )
    for phrase in ("BambooWorkbench/releases", "SHA-256", "无需 GitHub Token"):
        assert phrase in document

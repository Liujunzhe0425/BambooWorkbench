from pathlib import Path

from core.updates.service import DEFAULT_RELEASE_API

ROOT = Path(__file__).parents[2]


def test_default_updater_uses_public_binary_repository() -> None:
    assert DEFAULT_RELEASE_API == (
        "https://api.github.com/repos/Liujunzhe0425/"
        "BambooWorkbench-Distribution/releases/latest"
    )
    assert "/BambooWorkbench/releases/latest" not in DEFAULT_RELEASE_API


def test_public_release_script_verifies_visibility_assets_and_digests() -> None:
    script = (ROOT / "scripts" / "publish_public_release.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "BambooWorkbench-Distribution" in script
    assert "visibility -ne 'PUBLIC'" in script
    assert "Get-FileHash" in script
    assert "SHA256SUMS.txt" in script
    assert "^sha256:[0-9a-f]{64}$" in script
    assert "api_key" not in script.casefold()
    assert "BAMBOO_UPDATE_TOKEN" not in script


def test_public_distribution_document_keeps_source_and_secrets_private() -> None:
    document = (
        ROOT / "docs" / "release" / "public-binary-distribution.md"
    ).read_text(encoding="utf-8")
    for phrase in ("不得包含源码", "客户数据", "API Key", "GitHub Token"):
        assert phrase in document

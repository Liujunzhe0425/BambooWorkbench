import hashlib
from pathlib import Path

import httpx
import pytest

from core.updates.service import GitHubReleaseUpdateService, UpdateError


def _release_payload(content: bytes, *, version: str = "1.2.0") -> dict[str, object]:
    return {
        "tag_name": f"v{version}",
        "name": f"BambooWorkbench {version}",
        "html_url": (
            "https://github.com/Liujunzhe0425/"
            f"BambooWorkbench-Distribution/releases/tag/v{version}"
        ),
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": f"BambooWorkbench-Setup-{version}.exe",
                "url": "https://api.github.com/repos/Liujunzhe0425/"
                "BambooWorkbench-Distribution/releases/assets/123",
                "size": len(content),
                "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
            }
        ],
    }


def test_public_check_is_anonymous_and_download_verifies_hash(
    tmp_path: Path,
) -> None:
    content = b"synthetic-installer"
    seen_authorization: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_authorization.append(request.headers.get("Authorization"))
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(200, json=_release_payload(content), request=request)
        return httpx.Response(200, content=content, request=request)

    service = GitHubReleaseUpdateService(transport=httpx.MockTransport(handler))

    release = service.check("1.1.0")
    assert release is not None
    assert release.version == "1.2.0"
    installer = service.download(release, tmp_path)

    assert installer.read_bytes() == content
    assert seen_authorization == [None, None]


def test_check_ignores_equal_or_older_release() -> None:
    content = b"installer"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=_release_payload(content, version="1.1.0"),
            request=request,
        )
    )

    assert GitHubReleaseUpdateService(transport=transport).check("1.1.0") is None


def test_check_rejects_release_without_trusted_digest() -> None:
    payload = _release_payload(b"installer")
    payload["assets"][0]["digest"] = None  # type: ignore[index]
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload, request=request)
    )

    with pytest.raises(UpdateError, match="元数据不完整"):
        GitHubReleaseUpdateService(transport=transport).check("1.1.0")


def test_download_removes_partial_file_when_hash_does_not_match(tmp_path: Path) -> None:
    declared = b"declared"
    actual = b"modified"
    payload = _release_payload(declared)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(200, json=payload, request=request)
        return httpx.Response(200, content=actual, request=request)

    service = GitHubReleaseUpdateService(transport=httpx.MockTransport(handler))
    release = service.check("1.1.0")
    assert release is not None

    with pytest.raises(UpdateError, match="校验失败"):
        service.download(release, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_public_distribution_404_has_actionable_message() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"message": "Not Found"}, request=request)
    )

    with pytest.raises(UpdateError, match="公开更新源暂不可用"):
        GitHubReleaseUpdateService(transport=transport).check("1.1.0")

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .models import ReleaseUpdate, semantic_version

DEFAULT_RELEASE_API = (
    "https://api.github.com/repos/Liujunzhe0425/"
    "BambooWorkbench/releases/latest"
)
_INSTALLER = re.compile(r"^BambooWorkbench-Setup-(\d+\.\d+\.\d+)\.exe$")
_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
_DOWNLOAD_HOSTS = frozenset(
    {
        "api.github.com",
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
_MAX_INSTALLER_SIZE = 500 * 1024 * 1024


class UpdateError(RuntimeError):
    """A safe, user-facing update failure."""


class GitHubReleaseUpdateService:
    def __init__(
        self,
        release_api: str = DEFAULT_RELEASE_API,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.release_api = _validated_https_url(release_api, {"api.github.com"})
        self.transport = transport

    def check(self, current_version: str, *, token: str | None = None) -> ReleaseUpdate | None:
        current = semantic_version(current_version)
        try:
            with self._client(token) as client:
                response = client.get(self.release_api)
                if response.status_code == 404:
                    raise UpdateError("公开更新源暂不可用，请稍后重试")
                response.raise_for_status()
                payload = response.json()
        except UpdateError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise UpdateError("检查更新失败，请稍后重试") from error
        if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
            raise UpdateError("更新源没有返回可用的正式版本")
        tag_name = payload.get("tag_name")
        if not isinstance(tag_name, str):
            raise UpdateError("更新源缺少有效版本号")
        try:
            latest = semantic_version(tag_name)
        except ValueError as error:
            raise UpdateError("更新源版本号格式无效") from error
        if latest <= current:
            return None
        version = tag_name.removeprefix("v")
        expected_name = f"BambooWorkbench-Setup-{version}.exe"
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateError("新版本没有可下载的 Windows 安装包")
        asset = next(
            (
                item
                for item in assets
                if isinstance(item, dict) and item.get("name") == expected_name
            ),
            None,
        )
        if asset is None:
            raise UpdateError("新版本没有匹配版本号的 Windows 安装包")
        name = asset.get("name")
        url = asset.get("url") or asset.get("browser_download_url")
        size = asset.get("size")
        digest = asset.get("digest")
        match = _DIGEST.fullmatch(digest) if isinstance(digest, str) else None
        if (
            not isinstance(name, str)
            or _INSTALLER.fullmatch(name) is None
            or not isinstance(url, str)
            or type(size) is not int
            or not 0 < size <= _MAX_INSTALLER_SIZE
            or match is None
        ):
            raise UpdateError("安装包元数据不完整，已拒绝自动更新")
        html_url = payload.get("html_url")
        return ReleaseUpdate(
            version=version,
            tag_name=tag_name,
            title=str(payload.get("name") or tag_name)[:160],
            notes_url=(
                _validated_https_url(html_url, {"github.com"})
                if isinstance(html_url, str)
                else "https://github.com/Liujunzhe0425/BambooWorkbench/releases"
            ),
            asset_name=name,
            asset_url=_validated_https_url(url, _DOWNLOAD_HOSTS),
            asset_size=size,
            sha256=match.group(1),
        )

    def download(
        self,
        release: ReleaseUpdate,
        destination_root: Path,
        *,
        token: str | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        destination_root = destination_root.resolve()
        destination_root.mkdir(parents=True, exist_ok=True)
        target = (destination_root / release.asset_name).resolve()
        if target.parent != destination_root or _INSTALLER.fullmatch(target.name) is None:
            raise UpdateError("安装包保存路径无效")
        partial = target.with_suffix(target.suffix + ".part")
        partial.unlink(missing_ok=True)
        digest = hashlib.sha256()
        received = 0
        try:
            with (
                self._client(token, download=True) as client,
                client.stream("GET", release.asset_url) as response,
            ):
                response.raise_for_status()
                _validated_https_url(str(response.url), _DOWNLOAD_HOSTS)
                with partial.open("xb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > release.asset_size:
                            raise UpdateError("下载内容超过发布记录大小")
                        stream.write(chunk)
                        digest.update(chunk)
                        if progress is not None:
                            progress(received, release.asset_size)
                    stream.flush()
                    os.fsync(stream.fileno())
            if received != release.asset_size:
                raise UpdateError("安装包下载不完整")
            if digest.hexdigest() != release.sha256:
                raise UpdateError("安装包完整性校验失败，已拒绝安装")
            os.replace(partial, target)
            return target
        except UpdateError:
            partial.unlink(missing_ok=True)
            raise
        except (OSError, httpx.HTTPError) as error:
            partial.unlink(missing_ok=True)
            raise UpdateError("下载安装包失败，请稍后重试") from error

    def _client(self, token: str | None, *, download: bool = False) -> httpx.Client:
        headers = {
            "Accept": "application/octet-stream" if download else "application/vnd.github+json",
            "User-Agent": "BambooWorkbench-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(60.0 if download else 10.0, connect=10.0),
            transport=self.transport,
        )


def _validated_https_url(value: str, allowed_hosts: set[str] | frozenset[str]) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise UpdateError("更新地址未通过安全校验")
    if parsed.username or parsed.password or parsed.fragment:
        raise UpdateError("更新地址包含不允许的内容")
    return value

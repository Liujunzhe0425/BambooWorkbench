"""Installation-instance lifecycle for install-root-owned v1.3 data."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.platform.paths import AppPaths
from core.security.credentials import CredentialStore
from core.storage.settings import SettingsStore

INSTALL_MARKER_SCHEMA_VERSION = 1
KNOWN_CREDENTIAL_IDS = ("deepseek", "openai-compatible", "github-updates")


@dataclass(frozen=True, slots=True)
class InstallationState:
    instance_id: str
    created_at: str
    fresh: bool


def inspect_installation(paths: AppPaths) -> InstallationState | None:
    marker = paths.install_marker
    if not marker.exists():
        return None
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("安装实例标记不是可信的普通文件")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("marker must be an object")
        if payload.get("schema_version") != INSTALL_MARKER_SCHEMA_VERSION:
            raise ValueError("unsupported marker schema")
        instance_id = str(payload["instance_id"])
        created_at = str(payload["created_at"])
        if not instance_id or not created_at:
            raise ValueError("marker identity is empty")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("安装实例标记已损坏，已停止以避免误清理用户数据") from error
    return InstallationState(instance_id, created_at, False)


def prepare_installation(paths: AppPaths) -> InstallationState:
    existing = inspect_installation(paths)
    try:
        paths.ensure()
    except OSError as error:
        raise RuntimeError(
            f"安装目录不可写：{paths.root}。请调整目录权限后再启动。"
        ) from error
    _assert_root_writable(paths.root)
    if existing is not None:
        return existing
    _reset_fresh_internal_state(paths)
    return InstallationState(
        instance_id=uuid4().hex,
        created_at=datetime.now().astimezone().isoformat(),
        fresh=True,
    )


def complete_fresh_installation(
    paths: AppPaths,
    state: InstallationState,
    settings: SettingsStore,
    credentials: CredentialStore,
    *,
    clear_credentials: bool = True,
) -> None:
    if not state.fresh:
        return
    if clear_credentials:
        for credential_id in KNOWN_CREDENTIAL_IDS:
            credentials.delete_secret(credential_id)
    settings.set("ai_network_enabled", "false")
    settings.set("output_dir", str(paths.output))
    payload = {
        "schema_version": INSTALL_MARKER_SCHEMA_VERSION,
        "instance_id": state.instance_id,
        "created_at": state.created_at,
    }
    _atomic_write_json(paths.install_marker, payload)


def _assert_root_writable(root: Path) -> None:
    try:
        descriptor, name = tempfile.mkstemp(dir=root, prefix=".bamboo-write-test-")
        os.close(descriptor)
        Path(name).unlink()
    except OSError as error:
        raise RuntimeError(
            f"安装目录不可写：{root}。请调整目录权限后再启动。"
        ) from error


def _reset_fresh_internal_state(paths: AppPaths) -> None:
    """Remove packaged/residual runtime state while preserving source and output."""

    for target in (
        paths.database.parent,
        paths.tasks,
        paths.knowledge,
        paths.module_data,
        paths.logs,
        paths.cache,
    ):
        resolved = target.resolve()
        if not resolved.is_relative_to(paths.root.resolve()):
            raise RuntimeError("fresh-install reset target escaped the installation root")
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            continue
        for child in tuple(target.iterdir()):
            is_junction = getattr(child, "is_junction", None)
            if child.is_symlink() or bool(is_junction and is_junction()):
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

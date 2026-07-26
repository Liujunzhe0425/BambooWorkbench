"""Safely publish task-local artifacts to a user-selected output directory."""

import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.contracts.enums import ModuleId
from core.contracts.result import ModuleResult, OutputArtifact
from core.platform.path_safety import (
    resolve_contained_directory,
    resolve_contained_file,
    resolve_path,
)
from core.tasks.output_manifest import OutputManifestMetadata, write_output_manifest

_MODULE_NAMES = {
    ModuleId.MOISTURE: "竹丝水分",
    ModuleId.BOILING: "水煮实验",
    ModuleId.AFTER_SALES: "售后分析",
}
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def publish_outputs(
    result: ModuleResult,
    *,
    task_number: int | None = None,
    task_name: str | None = None,
    task_dir: Path,
    task_output_dir: Path,
    configured_root: str,
    manifest_metadata: OutputManifestMetadata | None = None,
    folder_timestamp: datetime | None = None,
) -> ModuleResult:
    """Copy a task's generated files and return a host-facing result copy.

    The module continues to see only its task-local sandbox.  The configured
    external directory is used after the module has exited successfully.
    """

    root_text = configured_root.strip()
    if not root_text:
        return result

    trusted_task_dir = resolve_contained_directory(
        task_dir, task_dir.parent, "task directory", reject_link=True
    )
    source = resolve_contained_directory(
        task_output_dir, trusted_task_dir, "task output directory", reject_link=True
    )
    root = resolve_path(
        Path(root_text).expanduser(), "configured output directory", strict=False
    )
    root.mkdir(parents=True, exist_ok=True)
    if _is_link(root) or not root.is_dir():
        raise ValueError("配置的输出目录不可用")
    root = root.resolve(strict=True)
    if root.is_relative_to(source):
        raise ValueError("输出目录不能位于任务内部输出目录中")

    timestamp = (folder_timestamp or result.finished_at).astimezone().strftime(
        "%Y%m%d-%H%M%S"
    )
    module_name = _UNSAFE_NAME.sub("_", _MODULE_NAMES[result.module_id]).strip(" .")
    safe_task_name = _UNSAFE_NAME.sub("_", task_name or module_name).strip(" .")
    if not safe_task_name:
        safe_task_name = module_name
    safe_task_name = safe_task_name[:96].rstrip(" .")
    base_name = f"{safe_task_name}-{timestamp}"
    # Compatibility for callers that have not yet adopted v1.3 task names.
    if task_name is None and task_number is not None:
        base_name = f"{task_number:06d}-{module_name}-{timestamp}"
    destination = _unique_destination(root, base_name)
    staging = root / f".bamboo-publish-{uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)

    try:
        _copy_declared_outputs(result.outputs, source, staging)
        if task_name is None:
            legacy_result = source / "result.json"
            if legacy_result.is_file() and not _is_link(legacy_result):
                shutil.copy2(legacy_result, staging / "result.json")
        published: list[OutputArtifact] = []
        for artifact in result.outputs:
            source_file = resolve_contained_file(
                Path(artifact.path), source, "output artifact", reject_link=True
            )
            relative = source_file.relative_to(source)
            published_file = staging / relative
            if not published_file.is_file():
                raise OSError(f"输出文件复制不完整：{relative.name}")
            published.append(artifact.model_copy(update={"path": str(published_file)}))
        if manifest_metadata is not None:
            write_output_manifest(staging, manifest_metadata, published)
        staging.rename(destination)
        published = [
            artifact.model_copy(
                update={"path": str(destination / Path(artifact.path).relative_to(staging))}
            )
            for artifact in published
        ]
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result.model_copy(update={"outputs": published})


def _unique_destination(root: Path, base_name: str) -> Path:
    candidate = root / base_name
    suffix = 2
    while candidate.exists():
        candidate = root / f"{base_name}-{suffix}"
        suffix += 1
    return candidate


def _copy_declared_outputs(
    artifacts: list[OutputArtifact], source: Path, destination: Path
) -> None:
    for artifact in artifacts:
        item = resolve_contained_file(
            Path(artifact.path), source, "output artifact", reject_link=True
        )
        relative = item.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())

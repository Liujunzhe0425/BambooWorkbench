"""Safely publish task-local artifacts to a user-selected output directory."""

import re
import shutil
from pathlib import Path

from core.contracts.enums import ModuleId
from core.contracts.result import ModuleResult, OutputArtifact
from core.platform.path_safety import (
    resolve_contained_directory,
    resolve_contained_file,
    resolve_path,
)

_MODULE_NAMES = {
    ModuleId.MOISTURE: "竹丝水分",
    ModuleId.BOILING: "水煮实验",
    ModuleId.AFTER_SALES: "售后分析",
}
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def publish_outputs(
    result: ModuleResult,
    *,
    task_number: int,
    task_dir: Path,
    task_output_dir: Path,
    configured_root: str,
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

    timestamp = result.finished_at.astimezone().strftime("%Y%m%d-%H%M%S")
    module_name = _UNSAFE_NAME.sub("_", _MODULE_NAMES[result.module_id]).strip(" .")
    base_name = f"{task_number:06d}-{module_name}-{timestamp}"
    destination = _unique_destination(root, base_name)
    destination.mkdir(parents=False, exist_ok=False)

    try:
        _copy_tree_without_links(source, destination)
        published: list[OutputArtifact] = []
        for artifact in result.outputs:
            source_file = resolve_contained_file(
                Path(artifact.path), source, "output artifact", reject_link=True
            )
            relative = source_file.relative_to(source)
            published_file = destination / relative
            if not published_file.is_file():
                raise OSError(f"输出文件复制不完整：{relative.name}")
            published.append(artifact.model_copy(update={"path": str(published_file)}))
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return result.model_copy(update={"outputs": published})


def _unique_destination(root: Path, base_name: str) -> Path:
    candidate = root / base_name
    suffix = 2
    while candidate.exists():
        candidate = root / f"{base_name}-{suffix}"
        suffix += 1
    return candidate


def _copy_tree_without_links(source: Path, destination: Path) -> None:
    for item in source.rglob("*"):
        if _is_link(item):
            raise ValueError("输出目录包含不允许发布的链接文件")
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        else:
            raise ValueError("输出目录包含不支持的文件类型")


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())

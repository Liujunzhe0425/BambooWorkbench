import sys
from dataclasses import dataclass
from pathlib import Path

SOURCE_MODULE_DIRECTORIES = {
    "moisture": "竹丝水分",
    "boiling": "水煮模块",
    "after_sales": "售后分析",
}


def resolve_install_root() -> Path:
    """Return the installed executable directory for a frozen application.

    Source and test runs must pass an explicit data root to ``AppPaths`` or
    ``build_context``.  This prevents an ordinary development run from
    silently creating v1.3 data in the repository or on the system drive.
    """

    if not getattr(sys, "frozen", False):
        raise RuntimeError("源码运行必须显式指定 BambooWorkbench 数据根目录")
    return Path(sys.executable).resolve().parent


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    install_marker: Path
    source: Path
    output: Path
    output_roots_registry: Path
    modules: Path
    knowledge: Path
    tasks: Path
    logs: Path
    cache: Path
    module_data: Path

    @classmethod
    def for_root(cls, root: Path | None = None) -> "AppPaths":
        resolved = (root if root is not None else resolve_install_root()).resolve()
        return cls(
            root=resolved,
            database=resolved / "data" / "app.db",
            install_marker=resolved / ".bamboo-install.json",
            source=resolved / "source",
            output=resolved / "output",
            output_roots_registry=resolved / "data" / "output-roots.json",
            modules=resolved / "modules",
            knowledge=resolved / "knowledge",
            tasks=resolved / "tasks",
            logs=resolved / "logs",
            cache=resolved / "cache",
            module_data=resolved / "module-data",
        )

    def ensure(self) -> None:
        directories = (
            self.root,
            self.database.parent,
            self.source,
            self.output,
            self.modules,
            self.knowledge,
            self.tasks,
            self.logs,
            self.cache,
            self.module_data,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        for name in SOURCE_MODULE_DIRECTORIES.values():
            (self.source / name).mkdir(parents=True, exist_ok=True)

    def source_for_module(self, module_id: str) -> Path:
        try:
            name = SOURCE_MODULE_DIRECTORIES[module_id]
        except KeyError as error:
            raise ValueError(f"unknown module source directory: {module_id}") from error
        return self.source / name

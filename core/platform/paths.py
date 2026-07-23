from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    modules: Path
    knowledge: Path
    tasks: Path
    logs: Path
    cache: Path
    module_data: Path

    @classmethod
    def for_root(cls, root: Path | None = None) -> "AppPaths":
        resolved = (root or user_data_path("BambooWorkbench", appauthor=False)).resolve()
        return cls(
            root=resolved,
            database=resolved / "data" / "app.db",
            modules=resolved / "modules",
            knowledge=resolved / "knowledge",
            tasks=resolved / "tasks",
            logs=resolved / "logs",
            cache=resolved / "cache",
            module_data=resolved / "module-data",
        )

    def ensure(self) -> None:
        directories = (
            self.database.parent,
            self.modules,
            self.knowledge,
            self.tasks,
            self.logs,
            self.cache,
            self.module_data,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

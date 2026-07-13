import platform

from app import __version__
from core.contracts.enums import ModuleId
from core.modules.registry import ModuleRegistry
from core.platform.paths import AppPaths


def collect_diagnostics(paths: AppPaths, registry: ModuleRegistry) -> dict[str, object]:
    modules: list[dict[str, object]] = []
    for module_id in ModuleId:
        try:
            registered = registry.get(module_id)
        except KeyError:
            continue
        modules.append(
            {
                "module_id": registered.manifest.module_id.value,
                "version": registered.manifest.module_version,
                "is_mock": registered.is_mock,
                "health": registered.health,
            }
        )
    return {
        "application_version": __version__,
        "python_version": platform.python_version(),
        "data_root": str(paths.root),
        "modules": modules,
        "log_directory": str(paths.logs),
    }

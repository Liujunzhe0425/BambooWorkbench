import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from core.contracts.enums import ModuleId
from core.contracts.manifest import ModuleManifest
from core.contracts.validator import validate_module

from .healthcheck import run_healthcheck

if TYPE_CHECKING:
    from core.storage.repositories.modules import ModuleRepository


@dataclass(frozen=True)
class RegisteredModule:
    manifest: ModuleManifest
    path: Path
    is_mock: bool
    health: str = "unknown"


class ModuleRegistry:
    def __init__(
        self,
        real_root: Path,
        mock_root: Path,
        use_mocks: bool,
        repository: "ModuleRepository | None" = None,
    ) -> None:
        self.real_root = real_root
        self.mock_root = mock_root
        self.use_mocks = use_mocks
        self.repository = repository
        self._modules: dict[ModuleId, RegisteredModule] = {}

    def scan(self) -> dict[ModuleId, RegisteredModule]:
        self._modules.clear()
        root = self.mock_root if self.use_mocks else self.real_root
        is_mock = self.use_mocks
        if not root.is_dir():
            return {}

        try:
            module_directories = sorted(root.iterdir())
        except OSError:
            return {}

        for module_dir in module_directories:
            module = self._load_module(module_dir, is_mock)
            if module is None:
                continue
            self._modules[module.manifest.module_id] = module
            self.check_health(module.manifest.module_id)
        return dict(self._modules)

    def get(self, module_id: ModuleId) -> RegisteredModule:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise KeyError(f"module not registered: {module_id}") from exc

    def check_health(self, module_id: ModuleId) -> tuple[bool, str]:
        module = self.get(module_id)
        try:
            healthy, detail = run_healthcheck(module)
        except Exception as exc:
            healthy, detail = False, f"health check failed: {type(exc).__name__}"
        refreshed = replace(module, health="healthy" if healthy else "unhealthy")
        self._modules[module_id] = refreshed
        self._persist(refreshed)
        return healthy, detail

    def _load_module(self, module_dir: Path, is_mock: bool) -> RegisteredModule | None:
        try:
            if not module_dir.is_dir() or not validate_module(module_dir).ok:
                return None
            manifest = ModuleManifest.model_validate(
                json.loads((module_dir / "module.json").read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError):
            return None
        return RegisteredModule(manifest, module_dir.resolve(), is_mock)

    def _persist(self, module: RegisteredModule) -> None:
        if self.repository is None:
            return
        self.repository.upsert(
            module.manifest.module_id.value,
            module.manifest.module_version,
            str(module.path),
            module.is_mock,
            module.health,
        )

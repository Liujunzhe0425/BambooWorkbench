import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.contracts.enums import ModuleId
from core.contracts.manifest import ModuleManifest
from core.modules.healthcheck import run_healthcheck
from core.modules.registry import ModuleRegistry, RegisteredModule
from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.modules import ModuleRepository


@pytest.fixture
def module_repository(tmp_path: Path) -> Iterator[ModuleRepository]:
    database = Database.open(AppPaths.for_root(tmp_path / "state"))
    database.migrate()
    try:
        yield ModuleRepository(database)
    finally:
        database.close()


def _write_module(
    root: Path,
    module_id: ModuleId,
    *,
    version: str = "1.2.3",
    launcher: str = "@echo off\r\nexit /b 0\r\n",
) -> Path:
    module_dir = root / module_id.value
    module_dir.mkdir(parents=True)
    manifest = {
        "schema_version": "1.0",
        "module_id": module_id.value,
        "module_name": module_id.value,
        "module_version": version,
        "entrypoint": "run_module.cmd",
        "supported_extensions": [".xlsx"],
        "supports_single_file": True,
        "supports_batch": True,
        "supports_incremental": False,
        "requires_network": False,
    }
    (module_dir / "module.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (module_dir / "run_module.cmd").write_text(launcher, encoding="utf-8")
    for filename in ("README.md", "CHANGELOG.md", "requirements.txt"):
        (module_dir / filename).write_text("test\n", encoding="utf-8")
    for dirname in ("src", "tests", "samples", "docs"):
        (module_dir / dirname).mkdir()
    return module_dir


def _registered(module_dir: Path) -> RegisteredModule:
    manifest = ModuleManifest.model_validate_json(
        (module_dir / "module.json").read_text(encoding="utf-8")
    )
    return RegisteredModule(manifest=manifest, path=module_dir.resolve(), is_mock=False)


def test_registry_discovers_all_mock_modules() -> None:
    project_root = Path(__file__).parents[3]
    registry = ModuleRegistry(
        real_root=project_root / "modules",
        mock_root=project_root / "mock_modules",
        use_mocks=True,
    )

    discovered = registry.scan()

    assert set(discovered) == {
        ModuleId.MOISTURE,
        ModuleId.BOILING,
        ModuleId.AFTER_SALES,
    }
    assert registry.get(ModuleId.MOISTURE).is_mock is True
    assert registry.get(ModuleId.MOISTURE).health == "healthy"


def test_registry_scans_only_the_explicitly_selected_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    mock_root = tmp_path / "mock"
    _write_module(real_root, ModuleId.MOISTURE)
    _write_module(mock_root, ModuleId.BOILING)

    discovered = ModuleRegistry(real_root, mock_root, use_mocks=False).scan()

    assert set(discovered) == {ModuleId.MOISTURE}
    assert discovered[ModuleId.MOISTURE].is_mock is False


def test_scan_skips_invalid_packages_and_keeps_unhealthy_modules(
    tmp_path: Path, module_repository: ModuleRepository
) -> None:
    root = tmp_path / "modules"
    invalid = root / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "module.json").write_text("{invalid", encoding="utf-8")
    unhealthy = _write_module(
        root,
        ModuleId.AFTER_SALES,
        launcher="@echo off\r\necho broken 1>&2\r\nexit /b 7\r\n",
    )
    registry = ModuleRegistry(
        root, tmp_path / "mocks", use_mocks=False, repository=module_repository
    )

    discovered = registry.scan()

    assert set(discovered) == {ModuleId.AFTER_SALES}
    assert discovered[ModuleId.AFTER_SALES].health == "unhealthy"
    assert module_repository.list_all() == [
        {
            "module_id": "after_sales",
            "version": "1.2.3",
            "path": str(unhealthy.resolve()),
            "is_mock": False,
            "health": "unhealthy",
        }
    ]


def test_check_health_refreshes_framework_state_and_persistence(
    tmp_path: Path, module_repository: ModuleRepository
) -> None:
    root = tmp_path / "modules"
    module_dir = _write_module(
        root, ModuleId.MOISTURE, launcher="@echo off\r\nexit /b 2\r\n"
    )
    registry = ModuleRegistry(
        root, tmp_path / "mocks", use_mocks=False, repository=module_repository
    )
    registry.scan()
    (module_dir / "run_module.cmd").write_text(
        "@echo off\r\necho recovered\r\nexit /b 0\r\n", encoding="utf-8"
    )

    healthy, detail = registry.check_health(ModuleId.MOISTURE)

    assert healthy is True
    assert detail == "recovered"
    assert registry.get(ModuleId.MOISTURE).health == "healthy"
    assert module_repository.list_all()[0]["health"] == "healthy"


def test_healthcheck_prepends_running_python_to_path(tmp_path: Path) -> None:
    module_dir = _write_module(
        tmp_path,
        ModuleId.BOILING,
        launcher='@echo off\r\npython -c "import sys; print(sys.executable)"\r\n',
    )

    healthy, detail = run_healthcheck(_registered(module_dir))

    assert healthy is True
    assert Path(detail).resolve() == Path(sys.executable).resolve()


def test_healthcheck_reports_timeout_without_crashing(tmp_path: Path) -> None:
    module_dir = _write_module(
        tmp_path,
        ModuleId.BOILING,
        launcher='@echo off\r\npython -c "import time; time.sleep(2)"\r\n',
    )

    healthy, detail = run_healthcheck(_registered(module_dir), timeout_ms=50)

    assert healthy is False
    assert "timed out" in detail


def test_healthcheck_reports_process_start_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_dir = _write_module(tmp_path, ModuleId.BOILING)
    monkeypatch.setenv("COMSPEC", str(tmp_path / "missing-cmd.exe"))

    healthy, detail = run_healthcheck(_registered(module_dir))

    assert healthy is False
    assert "failed to start" in detail

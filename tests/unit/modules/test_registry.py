import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QProcess

from core.contracts.enums import ModuleId
from core.contracts.manifest import ModuleManifest
from core.modules import healthcheck
from core.modules.healthcheck import run_healthcheck
from core.modules.process_control import ProcessCleanupResult
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


def _wait_for_file(path: Path, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.01)
    return path.exists()


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


def test_healthcheck_accepts_spaces_and_unicode_in_launcher_path(tmp_path: Path) -> None:
    module_dir = _write_module(
        tmp_path / "安全 模块",
        ModuleId.BOILING,
        launcher="@echo off\r\necho safe\r\n",
    )

    healthy, detail = run_healthcheck(_registered(module_dir))

    assert healthy is True
    assert detail == "safe"


@pytest.mark.parametrize("metacharacter", ["&", "%", "^", "(", ")", "!"])
def test_healthcheck_accepts_cmd_path_metacharacters_without_expansion(
    tmp_path: Path, metacharacter: str
) -> None:
    module_dir = _write_module(
        tmp_path / f"unsafe{metacharacter}path",
        ModuleId.BOILING,
        launcher="@echo off\r\necho safe>expected-marker\r\necho safe\r\n",
    )

    healthy, detail = run_healthcheck(_registered(module_dir))

    assert healthy is True
    assert detail == "safe"
    assert (module_dir / "expected-marker").read_text().strip() == "safe"


def test_healthcheck_reports_timeout_without_crashing(tmp_path: Path) -> None:
    module_dir = _write_module(
        tmp_path,
        ModuleId.BOILING,
        launcher='@echo off\r\npython -c "import time; time.sleep(2)"\r\n',
    )

    healthy, detail = run_healthcheck(_registered(module_dir), timeout_ms=50)

    assert healthy is False
    assert "timed out" in detail


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree regression")
def test_healthcheck_timeout_terminates_child_process_tree(tmp_path: Path) -> None:
    module_dir = _write_module(
        tmp_path,
        ModuleId.BOILING,
        launcher="@echo off\r\npython child.py\r\n",
    )
    (module_dir / "child.py").write_text(
        "from pathlib import Path\n"
        "import time\n"
        "Path('child-started').write_text('started', encoding='utf-8')\n"
        "time.sleep(2.0)\n"
        "Path('delayed-sentinel').write_text('orphaned', encoding='utf-8')\n",
        encoding="utf-8",
    )

    healthy, detail = run_healthcheck(_registered(module_dir), timeout_ms=1_500)

    assert healthy is False
    assert "timed out" in detail
    assert _wait_for_file(module_dir / "child-started", 0.5)
    assert not _wait_for_file(module_dir / "delayed-sentinel", 2.2)


def test_healthcheck_reports_process_start_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_dir = _write_module(tmp_path, ModuleId.BOILING)
    monkeypatch.setattr(healthcheck.sys, "executable", str(tmp_path / "missing-python.exe"))

    healthy, detail = run_healthcheck(_registered(module_dir))

    assert healthy is False
    assert "failed to start" in detail


def test_healthcheck_cleans_up_process_that_times_out_while_starting(tmp_path: Path) -> None:
    module_dir = _write_module(tmp_path, ModuleId.BOILING)
    process = Mock()
    process.waitForStarted.return_value = False
    process.state.side_effect = [
        QProcess.ProcessState.Starting,
        QProcess.ProcessState.NotRunning,
    ]
    cleanup = Mock(
        return_value=ProcessCleanupResult(
            process_stopped=True,
            detail="module host stopped",
        )
    )

    healthy, detail = run_healthcheck(
        _registered(module_dir),
        process_factory=lambda: process,
        process_terminator=cleanup,
    )

    assert healthy is False
    assert "failed to start" in detail
    cleanup.assert_called_once_with(process)
    assert process.state.call_count == 2


def test_healthcheck_reports_host_cleanup_failure(tmp_path: Path) -> None:
    module_dir = _write_module(tmp_path, ModuleId.BOILING)
    process = Mock()
    process.waitForStarted.return_value = True
    process.waitForFinished.return_value = False
    cleanup = Mock(
        return_value=ProcessCleanupResult(
            process_stopped=False,
            detail="module host did not stop",
        )
    )

    healthy, detail = run_healthcheck(
        _registered(module_dir),
        timeout_ms=1,
        process_factory=lambda: process,
        process_terminator=cleanup,
    )

    assert healthy is False
    assert detail == (
        "health check timed out after 1 ms; cleanup failed: "
        "module host did not stop"
    )


def test_healthcheck_launches_internal_host_with_current_interpreter(tmp_path: Path) -> None:
    module_dir = _write_module(tmp_path / "模块 root", ModuleId.BOILING)
    process = Mock()
    process.waitForStarted.return_value = True
    process.waitForFinished.return_value = True
    process.readAll.return_value = b"ok"
    process.exitStatus.return_value = QProcess.ExitStatus.NormalExit
    process.exitCode.return_value = 0

    healthy, detail = run_healthcheck(
        _registered(module_dir), process_factory=lambda: process
    )

    assert healthy is True
    assert detail == "ok"
    process.setProgram.assert_called_once_with(sys.executable)
    process.setArguments.assert_called_once_with(
        [
            str(Path(healthcheck.__file__).with_name("process_host.py")),
            "--launcher",
            str((module_dir / "run_module.cmd").resolve()),
            "self-check",
        ]
    )
    process.setNativeArguments.assert_not_called()

from pathlib import Path

from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from core.contracts.management import ModuleManagementRequest
from core.contracts.manifest import ModuleManifest
from core.modules.management_runner import ModuleManagementRunner
from core.modules.registry import RegisteredModule


def _management_module(tmp_path: Path) -> RegisteredModule:
    module_dir = tmp_path / "management-module"
    module_dir.mkdir()
    (module_dir / "helper.py").write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("command")
parser.add_argument("--request", type=Path, required=True)
parser.add_argument("--response", type=Path, required=True)
args = parser.parse_args()
request = json.loads(args.request.read_text(encoding="utf-8"))
response = {
    "schema_version": "1.0",
    "request_id": request["request_id"],
    "module_id": request["module_id"],
    "operation": request["operation"],
    "status": "ok",
    "history_items": [{
        "history_id": "history-1",
        "display_name": "2026年4月水分汇总",
        "sha256": "a" * 64,
        "active": True,
    }],
    "experience_items": [],
    "imported_history_id": None,
    "error_code": None,
    "message": "目录读取完成",
}
args.response.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )
    (module_dir / "run_management.bat").write_text(
        "@python helper.py %*\n",
        encoding="utf-8",
    )
    manifest = ModuleManifest(
        schema_version="1.0",
        module_id=ModuleId.MOISTURE,
        module_name="测试水分模块",
        module_version="1.0.1",
        entrypoint="run_management.bat",
        management_entrypoint="run_management.bat",
        capabilities=["ai_report"],
        supported_extensions=[".xlsx"],
        supports_single_file=True,
        supports_batch=True,
        supports_incremental=False,
        requires_network=False,
    )
    return RegisteredModule(manifest, module_dir.resolve(), False, "healthy")


def test_management_runner_executes_narrow_contract(qtbot, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data_dir = tmp_path / "module-data"
    data_dir.mkdir()
    request = ModuleManagementRequest(
        schema_version="1.0",
        request_id="request-001",
        module_id=ModuleId.MOISTURE,
        operation="list_history_summaries",
        data_dir=str(data_dir.resolve()),
    )
    runner = ModuleManagementRunner(timeout_ms=10_000)
    completed = QSignalSpy(runner.completed)
    failed = QSignalSpy(runner.failed)

    runner.start(_management_module(tmp_path), request, workspace)
    qtbot.waitUntil(lambda: completed.count() + failed.count() == 1, timeout=15_000)

    assert failed.count() == 0
    response = completed.at(0)[0]
    assert response.history_items[0].history_id == "history-1"
    assert response.history_items[0].display_name == "2026年4月水分汇总"

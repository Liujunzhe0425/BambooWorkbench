import ast
import inspect
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.ports.experience_repository import ExperienceRepository  # noqa: E402


def test_runtime_port_and_entrypoint_remain_read_only_and_admin_free() -> None:
    assert {
        name for name, _ in inspect.getmembers(ExperienceRepository) if not name.startswith("_")
    } == {"get", "search"}
    for relative in ("run_module.bat", "src/moisture/cli.py"):
        text = (MODULE_ROOT / relative).read_text(encoding="utf-8")
        assert "experience_management" not in text
        assert "local_editable_repository" not in text


def test_admin_has_no_forbidden_runtime_dependencies() -> None:
    forbidden = {"fastapi", "uvicorn", "httpx", "requests", "sqlalchemy", "sqlite3"}
    for relative in (
        "src/moisture/adapters/experience/local_editable_repository.py",
        "src/moisture/application/experience_management.py",
        "src/moisture/tools/manage_experience.py",
    ):
        tree = ast.parse((MODULE_ROOT / relative).read_text(encoding="utf-8"))
        imports = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        }
        imports |= {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imports.isdisjoint(forbidden)

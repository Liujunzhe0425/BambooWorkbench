from __future__ import annotations

import ast
import re
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = MODULE_ROOT / "src" / "moisture"

FORBIDDEN_PACKAGES = {
    "argon2",
    "azure",
    "fastapi",
    "httpx",
    "openai",
    "requests",
    "sqlalchemy",
    "sqlite3",
    "uvicorn",
}
FORBIDDEN_PATH_PARTS = {
    "csrf",
    "gateway",
    "identity",
    "provider",
    "rules-ui",
    "rules-user",
    "session",
    "web",
}
ADMIN_MODULES = {
    "moisture.adapters.experience.local_editable_repository",
    "moisture.application.experience_management",
    "moisture.ports.experience_admin_repository",
    "moisture.tools.manage_experience",
}


def _imports(source: str) -> set[str]:
    tree = ast.parse(source)
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _runtime_modules() -> set[str]:
    imports_by_module: dict[str, set[str]] = {}
    for path in SOURCE_ROOT.rglob("*.py"):
        module = "moisture." + path.relative_to(SOURCE_ROOT).with_suffix("").as_posix().replace(
            "/", "."
        )
        imports_by_module[module] = {
            name
            for name in _imports(path.read_text(encoding="utf-8"))
            if name.startswith("moisture.")
        }
    pending = ["moisture.cli"]
    reached: set[str] = set()
    while pending:
        module = pending.pop()
        if module in reached:
            continue
        reached.add(module)
        pending.extend(imports_by_module.get(module, set()) - reached)
    return reached


def test_forbidden_import_scanner_detects_a_synthetic_violation() -> None:
    assert any(
        name.split(".", 1)[0] in FORBIDDEN_PACKAGES
        for name in _imports("from fastapi import FastAPI\n")
    )


def test_module_has_no_legacy_runtime_responsibilities() -> None:
    for path in SOURCE_ROOT.rglob("*.py"):
        relative_parts = {part.casefold() for part in path.relative_to(SOURCE_ROOT).parts}
        assert relative_parts.isdisjoint(FORBIDDEN_PATH_PARTS), path
        imported_roots = {
            name.split(".", 1)[0] for name in _imports(path.read_text(encoding="utf-8"))
        }
        assert imported_roots.isdisjoint(FORBIDDEN_PACKAGES), path

    dependencies = {
        re.split(r"[<>=!~\[]", line.strip(), maxsplit=1)[0].casefold()
        for line in (MODULE_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert dependencies.isdisjoint(FORBIDDEN_PACKAGES)
    assert not (MODULE_ROOT / "schemas" / "job.schema.json").exists()
    assert not (MODULE_ROOT / "schemas" / "result.schema.json").exists()


def test_formal_runtime_cannot_reach_offline_experience_management() -> None:
    reached = _runtime_modules()
    assert reached.isdisjoint(ADMIN_MODULES)
    assert "moisture.application.draft_orchestrator" in reached
    assert "moisture.application.finalize_orchestrator" in reached

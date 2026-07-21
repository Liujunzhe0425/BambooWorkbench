import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_three_real_modules_are_complete_release_inputs() -> None:
    expected = {"moisture", "boiling", "after_sales"}
    discovered: set[str] = set()

    for module_dir in (ROOT / "modules").iterdir():
        manifest_path = module_dir / "module.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        module_id = str(manifest["module_id"])
        discovered.add(module_id)
        assert (module_dir / str(manifest["entrypoint"])).is_file()
        assert (module_dir / "build_portable_runtime.ps1").is_file()

    assert discovered == expected


def test_moisture_merge_resources_required_by_runtime_are_present() -> None:
    module = ROOT / "modules/moisture"
    required = (
        "module.json",
        "requirements.txt",
        "pyproject.toml",
        "schemas",
        "rules",
        "experience",
        "templates",
        "samples",
        "src/moisture/__init__.py",
    )
    for relative_path in required:
        assert (module / relative_path).exists(), relative_path

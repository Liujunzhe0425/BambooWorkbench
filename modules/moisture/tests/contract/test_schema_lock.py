import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"
CANONICAL_DIR = ROOT / "contracts" / "schemas"
BUNDLED_DIR = MODULE_ROOT / "schemas" / "contracts"
SYNC_TOOL = MODULE_ROOT / "tools" / "sync_contract_schemas.py"
SCHEMA_NAMES = (
    "job-request.schema.json",
    "module-management-request.schema.json",
    "module-management-response.schema.json",
    "module-manifest.schema.json",
    "module-result.schema.json",
)


def _import_schema_lock():
    sys.path.insert(0, str(MODULE_ROOT / "src"))
    try:
        from moisture.contract import schema_lock
    finally:
        sys.path.pop(0)
    return schema_lock


def test_bundled_schemas_are_byte_identical_to_canonical() -> None:
    for name in SCHEMA_NAMES:
        assert (BUNDLED_DIR / name).read_bytes() == (CANONICAL_DIR / name).read_bytes()


def test_schema_lock_uses_relative_posix_paths_and_exact_hashes() -> None:
    lock_path = BUNDLED_DIR / "schema-lock.json"
    raw_lock = lock_path.read_text(encoding="utf-8")
    lock = json.loads(raw_lock)

    assert raw_lock == json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert set(lock) == {"schema_version", "schemas"}
    assert lock["schema_version"] == 1
    assert set(lock["schemas"]) == {
        f"schemas/contracts/{name}" for name in SCHEMA_NAMES
    }
    for relative_path, expected_hash in lock["schemas"].items():
        assert "\\" not in relative_path
        assert not Path(relative_path).is_absolute()
        actual_hash = hashlib.sha256((MODULE_ROOT / relative_path).read_bytes()).hexdigest()
        assert expected_hash == actual_hash


def test_sync_check_is_read_only_and_reports_no_drift() -> None:
    before = {
        path.relative_to(MODULE_ROOT).as_posix(): path.read_bytes()
        for path in BUNDLED_DIR.glob("*.json")
    }
    completed = subprocess.run(
        [sys.executable, str(SYNC_TOOL), "--check"],
        cwd=Path.home(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    after = {
        path.relative_to(MODULE_ROOT).as_posix(): path.read_bytes()
        for path in BUNDLED_DIR.glob("*.json")
    }

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert before == after


def test_runtime_schema_lock_uses_only_local_bundle(tmp_path: Path) -> None:
    schema_lock = _import_schema_lock()
    isolated_root = tmp_path / "module"
    shutil.copytree(MODULE_ROOT, isolated_root)
    shutil.rmtree(isolated_root.parent / "contracts", ignore_errors=True)

    assert schema_lock.collect_schema_lock_issues(isolated_root) == ()


def test_self_check_rejects_modified_bundled_schema(tmp_path: Path) -> None:
    isolated_root = tmp_path / "module"
    shutil.copytree(MODULE_ROOT, isolated_root)
    bundled = isolated_root / "schemas" / "contracts" / "job-request.schema.json"
    bundled.write_bytes(bundled.read_bytes() + b" ")
    environment = os.environ.copy()
    environment["BAMBOO_MODULE_PYTHON"] = sys.executable

    completed = subprocess.run(
        [str(isolated_root / "run_module.bat"), "self-check"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 4
    assert completed.stdout == ""
    assert "schema" in completed.stderr.lower()

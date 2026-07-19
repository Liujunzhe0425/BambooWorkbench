"""Static contract tests for the portable runtime build hook and BAT launcher.

These tests verify the build hook contract and repository hygiene WITHOUT
executing a real PyInstaller build.  They only inspect source files,
scripts, and git tracking state.

Ownership: CC + DeepSeek (R3-S1).  Do NOT modify core implementation,
run_module.bat, build_portable_runtime.ps1, or any file outside this one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
BUILD_HOOK = MODULE_ROOT / "build_portable_runtime.ps1"
LAUNCHER = MODULE_ROOT / "run_module.bat"
RUNTIME_PATHS = MODULE_ROOT / "src" / "moisture" / "runtime_paths.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_ls_files(*patterns: str) -> list[str]:
    """Return tracked paths matching one of the given patterns (case-insensitive)."""
    completed = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    paths = completed.stdout.splitlines()
    return [
        p
        for p in paths
        if any(re.search(pat, p, re.IGNORECASE) for pat in patterns)
    ]


# ---------------------------------------------------------------------------
# Build hook existence and basic structure
# ---------------------------------------------------------------------------


def test_build_hook_exists_and_is_readable() -> None:
    assert BUILD_HOOK.is_file(), "build_portable_runtime.ps1 must exist"


def test_build_hook_references_repository_venv() -> None:
    text = _read(BUILD_HOOK)

    assert ".venv" in text
    assert "Scripts\\python.exe" in text or "Scripts/python.exe" in text
    # Must import PyInstaller from the repository venv
    assert "import PyInstaller" in text
    assert "sys.version_info" in text
    assert "3.11" in text


def test_build_hook_has_error_action_preference() -> None:
    text = _read(BUILD_HOOK)

    assert "$ErrorActionPreference" in text
    assert "Stop" in text


# ---------------------------------------------------------------------------
# Output target constraints
# ---------------------------------------------------------------------------


def test_build_hook_targets_portable_module_runtime() -> None:
    text = _read(BUILD_HOOK)

    assert "dist\\BambooWorkbench\\modules\\moisture" in text or \
           "dist/BambooWorkbench/modules/moisture" in text
    assert "runtime" in text


def test_build_hook_validates_portable_module_root_before_build() -> None:
    text = _read(BUILD_HOOK)

    assert "PortableModuleRoot" in text
    assert "module.json" in text
    assert "Test-Path" in text


# ---------------------------------------------------------------------------
# Repository boundary checks before deletion
# ---------------------------------------------------------------------------


def test_build_hook_has_repository_boundary_checks() -> None:
    text = _read(BUILD_HOOK)

    assert "Assert-RepositoryPath" in text
    assert "Remove-SafeTree" in text
    assert "ReparsePoint" in text
    assert "$RepositoryPrefix" in text


def test_build_hook_checks_resolved_path_stays_within_repository() -> None:
    text = _read(BUILD_HOOK)

    assert "[System.IO.Path]::GetFullPath" in text
    assert "$Resolved.StartsWith" in text


def test_build_hook_only_cleans_own_build_and_module_runtime_paths() -> None:
    text = _read(BUILD_HOOK)

    safe_remove_calls = re.findall(r"Remove-SafeTree\s+\$(\w+)", text)
    assert safe_remove_calls
    assert set(safe_remove_calls) <= {
        "BuildRoot",
        "IncomingRuntime",
        "BackupRuntime",
        "TargetRuntime",
    }
    assert "Remove-SafeTree $RepositoryRoot" not in text
    assert "Remove-SafeTree $PortableModuleRoot" not in text

    # Verify each Remove-SafeTree target is scoped to moisture
    for var_name in safe_remove_calls:
        # The variable should be defined with Assert-RepositoryPath pointing inside
        # dist\BambooWorkbench\modules\moisture\ or build\moisture-portable-runtime\
        pattern = rf"\${var_name}\s*=\s*Assert-RepositoryPath"
        assert re.search(pattern, text), (
            f"${var_name} must be initialized via Assert-RepositoryPath"
        )


# ---------------------------------------------------------------------------
# Build hook data collection
# ---------------------------------------------------------------------------


def test_build_hook_collects_required_frozen_resources() -> None:
    text = _read(BUILD_HOOK)

    required_resources = ["schemas", "rules", "experience", "templates"]
    for resource in required_resources:
        assert resource in text, f"Build hook must collect '{resource}'"


def test_build_hook_collects_module_metadata_files() -> None:
    text = _read(BUILD_HOOK)

    assert "module.json" in text
    assert "run_module.bat" in text
    assert "requirements.txt" in text
    assert "pyproject.toml" in text


# ---------------------------------------------------------------------------
# Atomic runtime replacement
# ---------------------------------------------------------------------------


def test_build_hook_has_atomic_runtime_replacement() -> None:
    text = _read(BUILD_HOOK)

    assert ".runtime.incoming" in text
    assert ".runtime.previous" in text
    assert "Move-Item" in text


def test_build_hook_rolls_back_on_failure() -> None:
    text = _read(BUILD_HOOK)

    # On failure, should restore previous runtime from backup
    assert "catch" in text.lower() or "try" in text.lower()
    assert "BackupRuntime" in text
    assert "Incomplete" in text


# ---------------------------------------------------------------------------
# Build hook repeatability and cleanup
# ---------------------------------------------------------------------------


def test_build_hook_cleans_build_root_before_building() -> None:
    text = _read(BUILD_HOOK)

    assert "BuildRoot" in text
    assert "moisture-portable-runtime" in text


def test_build_hook_does_not_auto_install_dependencies() -> None:
    text = _read(BUILD_HOOK)

    assert "pip install" not in text
    assert "Install-Module" not in text
    assert "Install-Package" not in text


# ---------------------------------------------------------------------------
# BAT launcher — frozen executable discovery
# ---------------------------------------------------------------------------


def test_bat_discovers_bundled_frozen_executable() -> None:
    text = _read(LAUNCHER)

    assert r"runtime\BambooMoistureModule.exe" in text or \
           "runtime/BambooMoistureModule.exe" in text
    assert "Bundled_executable" in text.lower() or \
           "bundled_executable" in text


def test_bat_bundled_runtime_before_development_python() -> None:
    text = _read(LAUNCHER)

    bundled_pos = text.find("BambooMoistureModule.exe")
    explicit_python_pos = text.find("BAMBOO_MODULE_PYTHON")
    virtual_env_pos = text.find("if defined VIRTUAL_ENV")

    # Bundled EXE should be checked before any Python fallback
    assert bundled_pos > 0
    assert bundled_pos < explicit_python_pos
    assert bundled_pos < virtual_env_pos


def test_bat_explicit_executable_has_highest_priority() -> None:
    text = _read(LAUNCHER)

    exec_pos = text.find("BAMBOO_MODULE_EXECUTABLE")
    bundled_pos = text.find("BambooMoistureModule.exe")
    # Explicit override must come before bundled auto-discovery
    assert exec_pos > 0
    assert exec_pos < bundled_pos


def test_bat_packaged_executable_missing_reports_error() -> None:
    text = _read(LAUNCHER)

    assert "packaged_executable_missing" in text
    assert "does not identify" in text


# ---------------------------------------------------------------------------
# runtime_paths — frozen mode support
# ---------------------------------------------------------------------------


def test_runtime_paths_supports_frozen_mode() -> None:
    text = _read(RUNTIME_PATHS)

    assert "sys.frozen" in text or "getattr(sys, \"frozen\"" in text
    assert "sys._MEIPASS" in text or "_MEIPASS" in text
    assert "modules" in text
    assert "moisture" in text


def test_runtime_paths_returns_module_root_for_source_mode() -> None:
    """In source mode module_root() resolves from __file__ parents."""
    text = _read(RUNTIME_PATHS)

    assert "__file__" in text
    assert "parents" in text


# ---------------------------------------------------------------------------
# No hardcoded absolute paths
# ---------------------------------------------------------------------------


def test_source_code_has_no_dev_machine_absolute_paths() -> None:
    """Scan Python source files for hardcoded absolute paths on this machine."""
    source_root = MODULE_ROOT / "src"
    suspicious: list[str] = []

    for py_file in source_root.rglob("*.py"):
        content = _read(py_file)
        for lineno, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Look for Windows absolute paths in string literals
            match = re.search(r"['\"]([A-Za-z]:\\[^'\"]{10,})['\"]", stripped)
            if match:
                path = match.group(1)
                # Allow runtime_paths sys._MEIPASS reference
                if "_MEIPASS" in stripped:
                    continue
                # Allow paths constructed from variables
                if any(
                    var in stripped
                    for var in ("__file__", "MODULE_ROOT", "REPO_ROOT", "Path(", "join")
                ):
                    continue
                suspicious.append(f"{py_file.name}:{lineno}: {path}")

    assert not suspicious, "Found hardcoded absolute paths:\n" + "\n".join(suspicious)


def test_manifest_has_no_absolute_paths() -> None:
    manifest = MODULE_ROOT / "module.json"
    text = _read(manifest)

    assert "C:\\" not in text
    assert "D:\\" not in text
    assert "Users\\" not in text


def test_build_hook_has_no_hardcoded_user_or_machine_paths() -> None:
    text = _read(BUILD_HOOK)

    assert "C:\\Users\\" not in text
    assert "D:\\Users\\" not in text


# ---------------------------------------------------------------------------
# Git tracking hygiene
# ---------------------------------------------------------------------------


def test_git_tracking_excludes_exe_files() -> None:
    tracked = _git_ls_files(r"\.exe$")
    assert not tracked, f".exe files tracked in git: {tracked}"


def test_git_tracking_excludes_module_runtime_directory() -> None:
    tracked = _git_ls_files(r"modules[/\\]moisture[/\\]runtime[/\\]")
    assert not tracked, f"module runtime/ tracked in git: {tracked}"


def test_git_tracking_excludes_build_and_dist() -> None:
    tracked = _git_ls_files(r"\b(build|dist)\b")
    assert not tracked, f"build/dist files tracked in git: {tracked}"


def test_git_tracking_excludes_dot_venv() -> None:
    tracked = _git_ls_files(r"\.venv[/\\]")
    assert not tracked, f".venv files tracked in git: {tracked}"


def test_gitignore_covers_portable_artifacts() -> None:
    repo_gitignore = REPOSITORY_ROOT / ".gitignore"
    text = _read(repo_gitignore)

    assert "dist/" in text
    assert "build/" in text
    assert ".venv/" in text


# ---------------------------------------------------------------------------
# Build hook error handling — dependency missing
# ---------------------------------------------------------------------------


def test_build_hook_reports_missing_venv_clearly() -> None:
    text = _read(BUILD_HOOK)

    assert "Repository virtual environment is unavailable" in text
    assert "throw" in text.lower()


def test_build_hook_reports_missing_pyinstaller_clearly() -> None:
    text = _read(BUILD_HOOK)

    assert "PyInstaller" in text
    assert "3.11" in text


def test_build_hook_reports_missing_portable_module_root_clearly() -> None:
    text = _read(BUILD_HOOK)

    assert "Portable module root has not been generated" in text


def test_build_hook_reports_missing_resource_clearly() -> None:
    text = _read(BUILD_HOOK)

    assert "Required frozen resource is missing" in text


# ---------------------------------------------------------------------------
# onedir layout expectations
# ---------------------------------------------------------------------------


def test_build_hook_uses_onedir_mode() -> None:
    text = _read(BUILD_HOOK)

    assert "--onedir" in text
    assert "BambooMoistureModule" in text
    assert "--contents-directory" in text
    assert "_internal" in text


def test_build_hook_does_not_use_onefile() -> None:
    text = _read(BUILD_HOOK)

    assert "--onefile" not in text

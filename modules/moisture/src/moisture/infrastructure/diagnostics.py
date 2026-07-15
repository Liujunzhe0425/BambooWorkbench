"""Local, network-free runtime diagnostics."""

import importlib
import sys
from pathlib import Path

MINIMUM_PYTHON = (3, 11)
REQUIRED_FILES = (
    "module.json",
    "run_module.bat",
    "README.md",
    "CHANGELOG.md",
    "requirements.txt",
    "pyproject.toml",
    "samples/README.md",
)


def collect_runtime_issues(module_root: Path | None = None) -> tuple[str, ...]:
    root = module_root or Path(__file__).resolve().parents[3]
    issues: list[str] = []

    if sys.version_info < MINIMUM_PYTHON:
        issues.append("Python 3.11 or newer is required")

    for relative_path in REQUIRED_FILES:
        if not (root / relative_path).is_file():
            issues.append(f"missing required file: {relative_path}")

    try:
        imported = importlib.import_module("moisture")
    except (ImportError, OSError) as error:
        issues.append(f"package import failed: {type(error).__name__}")
    else:
        if getattr(imported, "__version__", None) != "0.1.0":
            issues.append("package version does not match module manifest")

    return tuple(issues)

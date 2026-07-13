import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .manifest import ModuleManifest


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_module(module_dir: Path) -> ValidationReport:
    report = ValidationReport()
    manifest_path = module_dir / "module.json"
    if not manifest_path.is_file():
        report.issues.append(ValidationIssue("missing-module-json", "module.json is required"))
        report.issues.append(ValidationIssue("missing-entrypoint", "entrypoint cannot be resolved"))
        return report
    try:
        manifest = ModuleManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        report.issues.append(ValidationIssue("invalid-module-json", str(exc)))
        return report

    module_root = module_dir.resolve()
    entrypoint = Path(manifest.entrypoint)
    resolved_entrypoint = (module_root / entrypoint).resolve()
    if entrypoint.anchor or not resolved_entrypoint.is_relative_to(module_root):
        report.issues.append(
            ValidationIssue(
                "invalid-entrypoint",
                "entrypoint must be a relative path contained within the module directory",
            )
        )
    elif resolved_entrypoint.suffix.lower() not in {".bat", ".cmd"}:
        report.issues.append(
            ValidationIssue("invalid-entrypoint", "entrypoint must be a .bat or .cmd launcher")
        )
    elif resolved_entrypoint.is_dir():
        report.issues.append(
            ValidationIssue("invalid-entrypoint", "entrypoint must identify a file")
        )
    elif not resolved_entrypoint.is_file():
        report.issues.append(
            ValidationIssue("missing-entrypoint", f"missing file: {manifest.entrypoint}")
        )

    required_files = ["README.md", "CHANGELOG.md", "requirements.txt"]
    required_dirs = ["src", "tests", "samples", "docs"]
    for name in required_files:
        if not (module_dir / name).is_file():
            report.issues.append(ValidationIssue("missing-required-file", f"missing file: {name}"))
    for name in required_dirs:
        if not (module_dir / name).is_dir():
            report.issues.append(
                ValidationIssue("missing-required-directory", f"missing directory: {name}")
            )
    return report

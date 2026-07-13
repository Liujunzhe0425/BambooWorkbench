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
    required_files = ["README.md", "CHANGELOG.md", "requirements.txt", manifest.entrypoint]
    required_dirs = ["src", "tests", "samples", "docs"]
    for name in required_files:
        if not (module_dir / name).is_file():
            code = "missing-entrypoint" if name == manifest.entrypoint else "missing-required-file"
            report.issues.append(ValidationIssue(code, f"missing file: {name}"))
    for name in required_dirs:
        if not (module_dir / name).is_dir():
            report.issues.append(
                ValidationIssue("missing-required-directory", f"missing directory: {name}")
            )
    return report

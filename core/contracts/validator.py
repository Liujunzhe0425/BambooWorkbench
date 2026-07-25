import json
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
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
    _validate_entrypoint(report, module_root, manifest.entrypoint, "entrypoint", required=True)
    if manifest.management_entrypoint is not None:
        _validate_entrypoint(
            report,
            module_root,
            manifest.management_entrypoint,
            "management-entrypoint",
            required=False,
        )
    if manifest.management_contract is not None:
        if manifest.management_entrypoint is None:
            report.issues.append(
                ValidationIssue(
                    "missing-management-entrypoint",
                    "management_contract requires management_entrypoint",
                )
            )
        _validate_json_schema_asset(
            report,
            module_root,
            manifest.management_contract.request_schema,
            "management-request-schema",
        )
        _validate_json_schema_asset(
            report,
            module_root,
            manifest.management_contract.response_schema,
            "management-response-schema",
        )
    if len(manifest.capabilities) != len(set(manifest.capabilities)):
        report.issues.append(
            ValidationIssue("duplicate-capability", "module capabilities must be unique")
        )
    for capability in manifest.capabilities:
        if not capability or len(capability) > 64 or not all(
            character.islower() or character.isdigit() or character in {"_", "-"}
            for character in capability
        ):
            report.issues.append(
                ValidationIssue(
                    "invalid-capability",
                    f"invalid module capability: {capability}",
                )
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


def _validate_entrypoint(
    report: ValidationReport,
    module_root: Path,
    raw_entrypoint: str,
    code_prefix: str,
    *,
    required: bool,
) -> None:
    entrypoint = Path(raw_entrypoint)
    resolved = (module_root / entrypoint).resolve()
    invalid_code = f"invalid-{code_prefix}"
    missing_code = "missing-entrypoint" if required else f"missing-{code_prefix}"
    if entrypoint.anchor or not resolved.is_relative_to(module_root):
        report.issues.append(
            ValidationIssue(
                invalid_code,
                f"{code_prefix} must be a relative path contained within the module directory",
            )
        )
    elif resolved.suffix.lower() not in {".bat", ".cmd"}:
        report.issues.append(
            ValidationIssue(invalid_code, f"{code_prefix} must be a .bat or .cmd launcher")
        )
    elif resolved.is_dir():
        report.issues.append(
            ValidationIssue(invalid_code, f"{code_prefix} must identify a file")
        )
    elif not resolved.is_file():
        report.issues.append(ValidationIssue(missing_code, f"missing file: {raw_entrypoint}"))


def _validate_json_schema_asset(
    report: ValidationReport,
    module_root: Path,
    raw_path: str,
    code_prefix: str,
) -> None:
    relative = Path(raw_path)
    resolved = (module_root / relative).resolve()
    if relative.anchor or not resolved.is_relative_to(module_root):
        report.issues.append(
            ValidationIssue(
                f"invalid-{code_prefix}",
                f"{code_prefix} must be a relative path inside the module directory",
            )
        )
        return
    if resolved.suffix.casefold() != ".json" or not resolved.is_file() or resolved.is_symlink():
        report.issues.append(
            ValidationIssue(f"invalid-{code_prefix}", f"{code_prefix} must be a real JSON file")
        )
        return
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError):
        report.issues.append(
            ValidationIssue(f"invalid-{code_prefix}", f"{code_prefix} is not a valid JSON Schema")
        )

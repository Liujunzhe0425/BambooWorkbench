import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _is_sanitized_fixture(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    return normalized.startswith("tests/fixtures/") or (
        len(parts) >= 5
        and parts[0] == "modules"
        and bool(parts[1])
        and parts[2:4] == ["tests", "fixtures"]
    )


def test_repository_ignores_local_and_sensitive_artifacts() -> None:
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in (
        ".venv/",
        "*.db",
        "*.log",
        "data/",
        "dist/",
        "build/",
        ".env",
        "*.key",
        "installer-output/",
        "credentials/",
    ):
        assert required in rules


def test_repository_has_no_tracked_enterprise_spreadsheets() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    forbidden = [
        path
        for path in tracked
        if Path(path).suffix.lower() in {".xlsx", ".xls"}
        and not _is_sanitized_fixture(path)
    ]
    assert forbidden == []


def test_spreadsheet_fixture_scope_policy() -> None:
    assert _is_sanitized_fixture("tests/fixtures/shared/example.xlsx")
    assert _is_sanitized_fixture("modules/boiling/tests/fixtures/example.xlsx")
    assert not _is_sanitized_fixture("modules/boiling/samples/example.xlsx")
    assert not _is_sanitized_fixture("customer_data/example.xlsx")


def test_line_ending_policy_covers_code_docs_and_windows_scripts() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rule in ("*.py text eol=lf", "*.md text eol=lf", "*.ps1 text eol=crlf"):
        assert rule in attributes

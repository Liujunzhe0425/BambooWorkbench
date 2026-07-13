import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
        and not path.replace("\\", "/").startswith("tests/fixtures/")
    ]
    assert forbidden == []


def test_line_ending_policy_covers_code_docs_and_windows_scripts() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rule in ("*.py text eol=lf", "*.md text eol=lf", "*.ps1 text eol=crlf"):
        assert rule in attributes

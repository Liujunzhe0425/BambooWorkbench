import json
import sys
from pathlib import Path

import yaml

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.tools.manage_experience import main  # noqa: E402


def _write(path: Path, *, version: str = "1.0.0", body: str = "指导") -> None:
    payload = {
        "experience_id": "EXP-CLI",
        "version": version,
        "status": "draft",
        "title": "CLI 指导",
        "source": "offline/cli",
        "applicable_suppliers": ["*"],
        "applicable_materials": ["原竹丝"],
        "applicable_seasons": ["*"],
        "applicable_metrics": ["total_average"],
        "author": "author",
        "reviewer": "reviewer",
        "evidence_sources": ["evidence/cli"],
        "effective_at": "2026-01-01T00:00:00Z",
        "supersedes": None if version == "1.0.0" else "1.0.0",
    }
    path.write_text(
        f"---\n{yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)}---\n{body}\n",
        encoding="utf-8",
    )


def _call(root: Path, capsys, *arguments: str) -> dict:
    assert main(["--root", str(root), *arguments]) == 0
    return json.loads(capsys.readouterr().out)


def test_all_seven_offline_commands(tmp_path: Path, capsys) -> None:
    root = tmp_path / "store"
    document = tmp_path / "entry.md"
    _write(document)
    assert _call(root, capsys, "list") == []
    _call(root, capsys, "validate", "--document", str(document))
    created = _call(root, capsys, "create", "--document", str(document))
    shown = _call(root, capsys, "show", "EXP-CLI", "1.0.0")
    assert shown["sha256"] == created["sha256"]
    _write(document, body="修改")
    updated = _call(
        root,
        capsys,
        "update",
        "EXP-CLI",
        "1.0.0",
        "--expected-hash",
        created["sha256"],
        "--document",
        str(document),
    )
    approved = _call(
        root, capsys, "publish", "EXP-CLI", "1.0.0", "--expected-hash", updated["sha256"]
    )
    retired = _call(
        root, capsys, "retire", "EXP-CLI", "1.0.0", "--expected-hash", approved["sha256"]
    )
    assert retired["status"] == "retired"


def test_cli_reports_conflict_without_traceback(tmp_path: Path, capsys) -> None:
    root = tmp_path / "store"
    document = tmp_path / "entry.md"
    _write(document)
    _call(root, capsys, "create", "--document", str(document))
    assert (
        main(["--root", str(root), "publish", "EXP-CLI", "1.0.0", "--expected-hash", "0" * 64]) == 2
    )
    captured = capsys.readouterr()
    assert "hash" in captured.err
    assert "Traceback" not in captured.err

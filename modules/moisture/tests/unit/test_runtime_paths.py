from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.runtime_paths import module_root  # noqa: E402


def test_module_root_uses_source_module_directory() -> None:
    assert module_root() == Path(__file__).resolve().parents[2]


def test_module_root_uses_packaged_asset_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    assert module_root() == (tmp_path / "bundle" / "modules" / "moisture").resolve()

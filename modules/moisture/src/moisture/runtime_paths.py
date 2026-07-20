"""Resolve immutable module assets in source and frozen runtimes."""

from __future__ import annotations

import sys
from pathlib import Path


def module_root() -> Path:
    if getattr(sys, "frozen", False):
        return (Path(sys._MEIPASS) / "modules" / "moisture").resolve()
    return Path(__file__).resolve().parents[2]


__all__ = ["module_root"]

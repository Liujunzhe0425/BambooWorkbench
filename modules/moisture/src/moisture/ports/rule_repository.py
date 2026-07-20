"""Narrow read-only port for the bundled rule package."""

from pathlib import Path
from typing import Protocol

from moisture.domain.rules import RulePackageSnapshot


class RulePackageRepository(Protocol):
    def load(self, package_dir: Path) -> RulePackageSnapshot: ...

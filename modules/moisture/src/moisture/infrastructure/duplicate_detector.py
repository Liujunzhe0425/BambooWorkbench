"""Stable input planning for Office temporary files and duplicate content."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from moisture.domain.models import InputFileIdentity
from moisture.infrastructure.hashing import sha256_file

InputStatus = Literal["process", "skipped"]
InputReason = Literal["canonical", "duplicate_content", "office_temporary_file"]


@dataclass(frozen=True, slots=True)
class InputDecision:
    """One stable decision in the same order as the declared job inputs."""

    source_file: Path
    input_order: int
    status: InputStatus
    reason: InputReason
    message: str
    identity: InputFileIdentity | None = None
    canonical_input_order: int | None = None


class DuplicateDetector:
    """Keep the first occurrence of each content fingerprint."""

    def __init__(self, hasher: Callable[[Path], str] = sha256_file) -> None:
        self._hasher = hasher

    def classify(self, paths: Iterable[Path]) -> tuple[InputDecision, ...]:
        canonical_orders: dict[str, int] = {}
        decisions: list[InputDecision] = []

        for input_order, path in enumerate(paths):
            if _is_office_temporary_workbook(path):
                decisions.append(
                    InputDecision(
                        source_file=path,
                        input_order=input_order,
                        status="skipped",
                        reason="office_temporary_file",
                        message="Office temporary workbook skipped",
                    )
                )
                continue

            identity = InputFileIdentity(
                source_file=path,
                fingerprint=self._hasher(path),
                input_order=input_order,
            )
            canonical_input_order = canonical_orders.get(identity.fingerprint)
            if canonical_input_order is None:
                canonical_orders[identity.fingerprint] = input_order
                decisions.append(
                    InputDecision(
                        source_file=path,
                        input_order=input_order,
                        status="process",
                        reason="canonical",
                        message="canonical content",
                        identity=identity,
                        canonical_input_order=input_order,
                    )
                )
                continue

            decisions.append(
                InputDecision(
                    source_file=path,
                    input_order=input_order,
                    status="skipped",
                    reason="duplicate_content",
                    message=(
                        "duplicate content; canonical input order: "
                        f"{canonical_input_order}"
                    ),
                    identity=identity,
                    canonical_input_order=canonical_input_order,
                )
            )

        return tuple(decisions)


def _is_office_temporary_workbook(path: Path) -> bool:
    return path.name.startswith("~$") and path.suffix.casefold() == ".xlsx"

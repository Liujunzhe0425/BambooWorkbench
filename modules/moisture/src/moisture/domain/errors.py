"""Stable, non-sensitive error records owned by the moisture domain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProtocolReadError:
    """A protocol failure safe to pass to later orchestration layers."""

    code: str
    field: str
    message: str

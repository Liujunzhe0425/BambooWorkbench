"""Read input files while detecting changes made during the read."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from moisture.domain.models import InputFileIdentity
from moisture.infrastructure.hashing import sha256_file

T = TypeVar("T")


class SourceFileChangedError(RuntimeError):
    """Raised when an input fingerprint differs after a read attempt."""

    def __init__(
        self,
        source_file: Path,
        expected_fingerprint: str,
        actual_fingerprint: str,
    ) -> None:
        super().__init__("source file changed during read")
        self.source_file = source_file
        self.expected_fingerprint = expected_fingerprint
        self.actual_fingerprint = actual_fingerprint


@dataclass(frozen=True, slots=True)
class CheckedRead(Generic[T]):  # noqa: UP046 -- package supports Python 3.11
    """A reader result bound to the content fingerprint it consumed."""

    identity: InputFileIdentity
    value: T


class FileIntegrityGuard:
    """Compute content identity before a read and verify it afterwards."""

    def __init__(self, hasher: Callable[[Path], str] = sha256_file) -> None:
        self._hasher = hasher

    def snapshot(self, path: Path, input_order: int) -> InputFileIdentity:
        return InputFileIdentity(
            source_file=path,
            fingerprint=self._hasher(path),
            input_order=input_order,
        )

    def assert_unchanged(self, identity: InputFileIdentity) -> None:
        actual_fingerprint = self._hasher(identity.source_file)
        if actual_fingerprint != identity.fingerprint:
            raise SourceFileChangedError(
                source_file=identity.source_file,
                expected_fingerprint=identity.fingerprint,
                actual_fingerprint=actual_fingerprint,
            )

    def read_checked(
        self,
        path: Path,
        input_order: int,
        reader: Callable[[Path], T],
    ) -> CheckedRead[T]:
        """Run *reader* and ensure parser failures cannot hide input changes."""

        identity = self.snapshot(path, input_order)
        try:
            value = reader(path)
        except Exception as reader_error:
            try:
                self.assert_unchanged(identity)
            except SourceFileChangedError as integrity_error:
                raise integrity_error from reader_error
            raise
        self.assert_unchanged(identity)
        return CheckedRead(identity=identity, value=value)

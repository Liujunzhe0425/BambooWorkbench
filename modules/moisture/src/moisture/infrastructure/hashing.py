"""Content hashing migrated from the stable moisture implementation."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of *path* without loading the whole file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()

"""Resolved output path boundaries for module-owned artifacts."""

from pathlib import Path


class OutputPathError(ValueError):
    """An output is missing or escapes the job's authorized output directory."""


def require_existing_output(output_dir: Path, candidate: Path) -> Path:
    if not output_dir.is_absolute() or not candidate.is_absolute():
        raise OutputPathError("output directory and artifact paths must be absolute")
    try:
        root = output_dir.resolve(strict=True)
        artifact = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise OutputPathError("output artifact does not exist or cannot be resolved") from error
    if not root.is_dir() or not artifact.is_file():
        raise OutputPathError("output artifact must be a completed regular file")
    if not artifact.is_relative_to(root):
        raise OutputPathError("output artifact escapes output_dir")
    return artifact

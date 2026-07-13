import hashlib
import os
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Snapshot:
    source: Path
    copy: Path
    fingerprint: str


def remove_snapshots(snapshots: list[Snapshot]) -> None:
    input_directories: set[Path] = set()
    for snapshot in snapshots:
        snapshot.copy.unlink(missing_ok=True)
        input_directories.add(snapshot.copy.parent)
    for input_directory in input_directories:
        with suppress(OSError):
            input_directory.rmdir()


def _validate_inputs(inputs: list[Path], supported_extensions: list[str]) -> list[Path]:
    if not inputs:
        raise ValueError("at least one input file is required")
    extensions = {extension.casefold() for extension in supported_extensions}
    validated: list[Path] = []
    for input_path in inputs:
        source = Path(input_path)
        if not source.is_file():
            raise ValueError(f"input is not an existing regular file: {source}")
        if source.stat().st_size == 0:
            raise ValueError(f"input file must not be empty: {source}")
        if source.suffix.casefold() not in extensions:
            raise ValueError(f"unsupported input extension: {source.suffix or '<none>'}")
        validated.append(source.resolve(strict=True))
    return validated


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_inputs(
    inputs: list[Path], task_dir: Path, supported_extensions: list[str]
) -> list[Snapshot]:
    sources = _validate_inputs(inputs, supported_extensions)
    input_dir = task_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    snapshots: list[Snapshot] = []
    installed: list[Path] = []
    try:
        for index, source in enumerate(sources, start=1):
            target = input_dir / f"{index:03d}-{source.name}"
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{index:03d}-",
                    suffix=".tmp",
                    dir=input_dir,
                    delete=False,
                ) as output:
                    temporary = Path(output.name)
                    with source.open("rb") as source_stream:
                        shutil.copyfileobj(source_stream, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
                temporary = None
                installed.append(target)
                resolved_target = target.resolve(strict=True)
                snapshots.append(
                    Snapshot(
                        source=source,
                        copy=resolved_target,
                        fingerprint=_fingerprint(resolved_target),
                    )
                )
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    except Exception:
        for installed_path in reversed(installed):
            installed_path.unlink(missing_ok=True)
        with suppress(OSError):
            input_dir.rmdir()
        raise
    return snapshots

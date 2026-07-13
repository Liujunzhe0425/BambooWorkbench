from pathlib import Path


def resolve_path(path: Path, label: str, *, strict: bool) -> Path:
    try:
        return path.resolve(strict=strict)
    except RuntimeError as exc:
        raise ValueError(f"{label} path resolution failed: {exc}") from exc


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _reject_link(path: Path, label: str, reject_link: bool) -> None:
    if reject_link and _is_link(path):
        raise ValueError(f"{label} must not be a link")


def _resolve_contained(
    path: Path,
    root: Path,
    label: str,
    *,
    strict: bool,
    reject_link: bool,
) -> Path:
    resolved_root = resolve_path(root, f"{label} root", strict=True)
    _reject_link(path, label, reject_link)
    try:
        resolved = resolve_path(path, label, strict=strict)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} does not exist") from exc
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label} is outside root")
    return resolved


def resolve_contained_file(
    path: Path,
    root: Path,
    label: str,
    *,
    reject_link: bool = False,
) -> Path:
    resolved = _resolve_contained(
        path,
        root,
        label,
        strict=True,
        reject_link=reject_link,
    )
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file")
    return resolved


def resolve_contained_directory(
    path: Path,
    root: Path,
    label: str,
    *,
    reject_link: bool = False,
) -> Path:
    resolved = _resolve_contained(
        path,
        root,
        label,
        strict=True,
        reject_link=reject_link,
    )
    if not resolved.is_dir():
        raise ValueError(f"{label} is not a directory")
    return resolved


def resolve_contained_target(
    path: Path,
    root: Path,
    label: str,
    *,
    reject_link: bool = False,
) -> Path:
    return _resolve_contained(
        path,
        root,
        label,
        strict=False,
        reject_link=reject_link,
    )

from pathlib import Path


def launcher_validation_error(launcher: Path) -> str | None:
    if launcher.suffix.lower() not in {".bat", ".cmd"}:
        return "module launcher must be a .bat or .cmd file"
    if not launcher.is_file():
        return "module launcher does not exist"
    return None

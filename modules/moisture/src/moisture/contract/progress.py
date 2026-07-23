"""Strict stdout progress events understood by BambooWorkbench."""

import json
import sys


def emit_progress(percent: int, message: str, source_file: str | None = None) -> None:
    event: dict[str, object] = {
        "type": "progress",
        "percent": percent,
        "message": message,
    }
    if source_file is not None:
        event["source_file"] = source_file
    # Keep the process protocol ASCII-only. Frozen Windows executables can
    # otherwise encode Chinese progress text with the active console code page,
    # while BambooWorkbench intentionally decodes protocol lines as UTF-8.
    sys.stdout.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()

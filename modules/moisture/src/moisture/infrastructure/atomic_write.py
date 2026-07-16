"""Atomic UTF-8 JSON output confined to the destination directory."""

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from moisture.contract.result_models import ModuleResult
from moisture.contract.validators import validate_result_payload
from moisture.infrastructure.paths import OutputPathError, require_existing_output


def _write_json_atomic(destination: Path, payload: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        raise


class AtomicResultWriter:
    """Validate completed artifacts and publish ``result.json`` last."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def write(self, result: ModuleResult) -> Path:
        return self.write_payload(result.to_payload())

    def write_payload(self, payload: dict[str, Any]) -> Path:
        validated = validate_result_payload(payload)
        destination = self.output_dir / "result.json"
        for output in validated.outputs:
            artifact = require_existing_output(self.output_dir, output.path)
            if artifact == destination.resolve():
                raise OutputPathError(
                    "result.json cannot be registered as a business artifact"
                )
        _write_json_atomic(destination, validated.to_payload())
        return destination


def write_json_atomic(destination: Path, payload: dict[str, Any]) -> None:
    """Compatibility entry point; contract-shaped results use the guarded writer."""

    if destination.name == "result.json" and {
        "schema_version",
        "module_id",
        "status",
        "summary",
    }.issubset(payload):
        AtomicResultWriter(destination.parent).write_payload(payload)
        return
    _write_json_atomic(destination, payload)

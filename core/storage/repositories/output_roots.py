"""Known output-root persistence in SQLite and an installation-root JSON registry."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from core.platform.paths import AppPaths
from core.storage.database import Database


class OutputRootRepository:
    def __init__(self, database: Database, paths: AppPaths) -> None:
        self.database = database
        self.paths = paths

    def initialize_default(self) -> int:
        return self.set_current(self.paths.output, is_default=True)

    def restore_from_registry(self) -> int | None:
        path = self.paths.output_roots_registry
        if not path.is_file():
            return None
        payload = _read_registry_payload(path)
        current_text = payload.get("current_root")
        roots = [Path(item).expanduser().resolve() for item in payload["roots"] if item]
        default = self.paths.output.resolve()
        if default not in roots:
            roots.insert(0, default)
        current = Path(current_text).expanduser().resolve() if current_text else default
        if current not in roots:
            roots.append(current)
        now = datetime.now().astimezone().isoformat()
        with self.database.connection:
            for root in roots:
                self.database.connection.execute(
                    "INSERT INTO output_roots("
                    "path, is_default, is_current, created_at, last_seen_at"
                    ") VALUES (?, ?, ?, ?, ?) ON CONFLICT(path) DO NOTHING",
                    (str(root), int(root == default), int(root == current), now, now),
                )
        row = self.database.scalar(
            "SELECT id FROM output_roots WHERE path = ?", (str(current),)
        )
        return None if row is None else int(row)

    def set_current(self, path: Path, *, is_default: bool = False) -> int:
        if not path.expanduser().is_absolute():
            raise ValueError("成果根目录必须是绝对路径")
        resolved = path.expanduser().resolve()
        now = datetime.now().astimezone().isoformat()
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE output_roots SET is_current = 0 WHERE is_current = 1"
            )
            self.database.connection.execute(
                "INSERT INTO output_roots(path, is_default, is_current, created_at, last_seen_at) "
                "VALUES (?, ?, 1, ?, ?) ON CONFLICT(path) DO UPDATE SET "
                "is_default = MAX(output_roots.is_default, excluded.is_default), "
                "is_current = 1, last_seen_at = excluded.last_seen_at",
                (str(resolved), int(is_default), now, now),
            )
        row_id = int(
            self.database.scalar("SELECT id FROM output_roots WHERE path = ?", (str(resolved),))
        )
        self.write_registry()
        return row_id

    def list_all(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM output_roots ORDER BY is_default DESC, created_at, id"
        ).fetchall()
        return [dict(row) for row in rows]

    def current(self) -> dict[str, object]:
        row = self.database.connection.execute(
            "SELECT * FROM output_roots WHERE is_current = 1"
        ).fetchone()
        if row is None:
            self.initialize_default()
            return self.current()
        return dict(row)

    def get(self, root_id: int) -> dict[str, object]:
        row = self.database.connection.execute(
            "SELECT * FROM output_roots WHERE id = ?", (root_id,)
        ).fetchone()
        if row is None:
            raise KeyError(root_id)
        return dict(row)

    def write_registry(self) -> None:
        roots = self.list_all()
        current = next((str(item["path"]) for item in roots if item["is_current"]), None)
        payload = {
            "schema_version": 1,
            "current_root": current,
            "roots": [str(item["path"]) for item in roots],
        }
        _atomic_write(self.paths.output_roots_registry, payload)

    def read_registry(self) -> tuple[Path, ...]:
        path = self.paths.output_roots_registry
        if not path.exists():
            return (self.paths.output.resolve(),)
        try:
            payload = _read_registry_payload(path)
            roots = [self.paths.output.resolve()]
            roots.extend(Path(item).expanduser().resolve() for item in payload["roots"] if item)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("成果根目录登记文件已损坏") from error
        return tuple(dict.fromkeys(roots))


def _read_registry_payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported output-root registry")
    if not isinstance(payload.get("roots"), list):
        raise ValueError("unsupported output-root registry")
    current = payload.get("current_root")
    if current is not None and not isinstance(current, str):
        raise ValueError("unsupported output-root registry")
    return payload


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

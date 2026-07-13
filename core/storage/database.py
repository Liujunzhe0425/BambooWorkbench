import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.platform.paths import AppPaths


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATION_1 = Migration(
    version=1,
    statements=(
        """
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    ),
)

MIGRATIONS: tuple[Migration, ...] = (MIGRATION_1,)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    @classmethod
    def open(cls, paths: AppPaths) -> "Database":
        paths.ensure()
        return cls(paths.database)

    def migrate(self) -> None:
        self._ensure_schema_version()
        current = int(self.scalar("SELECT version FROM schema_version"))

        for migration in MIGRATIONS:
            if migration.version <= current:
                continue
            if migration.version != current + 1:
                raise ValueError(
                    f"Expected migration version {current + 1}, got {migration.version}"
                )
            self._apply_migration(migration)
            current = migration.version

    def _ensure_schema_version(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            self.connection.execute(
                "INSERT INTO schema_version(version) "
                "SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version)"
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _apply_migration(self, migration: Migration) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                self.connection.execute(statement)
            self.connection.execute(
                "UPDATE schema_version SET version = ?", (migration.version,)
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(sql, parameters)
        self.connection.commit()
        return cursor

    def scalar(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        row = self.connection.execute(sql, parameters).fetchone()
        return None if row is None else row[0]

    def close(self) -> None:
        self.connection.close()

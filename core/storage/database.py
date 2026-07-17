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

MIGRATION_2 = Migration(
    version=2,
    statements=(
        """
        CREATE TABLE tasks (
            job_id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            parent_job_id TEXT REFERENCES tasks(job_id) ON DELETE SET NULL,
            result_path TEXT,
            error TEXT
        )
        """,
        """
        CREATE TABLE task_files (
            job_id TEXT NOT NULL REFERENCES tasks(job_id) ON DELETE CASCADE,
            source_path TEXT NOT NULL,
            snapshot_path TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY(job_id, source_path)
        )
        """,
        """
        CREATE TABLE modules (
            module_id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            path TEXT NOT NULL,
            is_mock INTEGER NOT NULL,
            health TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE confirmations (
            job_id TEXT NOT NULL REFERENCES tasks(job_id) ON DELETE CASCADE,
            confirmation_id TEXT NOT NULL,
            original_prompt TEXT NOT NULL,
            answer TEXT,
            answered_at TEXT,
            PRIMARY KEY(job_id, confirmation_id)
        )
        """,
        """
        CREATE TABLE outputs (
            job_id TEXT NOT NULL REFERENCES tasks(job_id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            path TEXT NOT NULL,
            label TEXT NOT NULL
        )
        """,
    ),
)

MIGRATION_3 = Migration(
    version=3,
    statements=(
        """
        CREATE TABLE ai_consent_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            allowed INTEGER NOT NULL,
            data_categories_json TEXT NOT NULL,
            decided_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX idx_ai_consent_task ON ai_consent_audit(task_id)",
    ),
)

MIGRATION_4 = Migration(
    version=4,
    statements=(
        """
        CREATE TABLE knowledge_records (
            record_id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            source_path TEXT
        )
        """,
        "CREATE INDEX idx_knowledge_namespace ON knowledge_records(namespace, enabled)",
    ),
)

MIGRATION_5 = Migration(
    version=5,
    statements=(
        "ALTER TABLE tasks ADD COLUMN module_config_hash TEXT",
    ),
)

MIGRATIONS: tuple[Migration, ...] = (
    MIGRATION_1,
    MIGRATION_2,
    MIGRATION_3,
    MIGRATION_4,
    MIGRATION_5,
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

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

    def query_all(
        self, sql: str, parameters: tuple[Any, ...] = ()
    ) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, parameters).fetchall())

    def close(self) -> None:
        self.connection.close()

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
        "ALTER TABLE tasks ADD COLUMN task_name TEXT",
        "ALTER TABLE tasks ADD COLUMN period_year INTEGER "
        "CHECK(period_year IS NULL OR period_year BETWEEN 2000 AND 9999)",
        "ALTER TABLE tasks ADD COLUMN period_month INTEGER "
        "CHECK(period_month IS NULL OR period_month BETWEEN 1 AND 12)",
        "ALTER TABLE tasks ADD COLUMN learning_enabled INTEGER NOT NULL DEFAULT 1 "
        "CHECK(learning_enabled IN (0, 1))",
        "ALTER TABLE tasks ADD COLUMN candidate_for_job_id TEXT "
        "REFERENCES tasks(job_id) ON DELETE SET NULL",
        "ALTER TABLE tasks ADD COLUMN output_root_id INTEGER REFERENCES output_roots(id)",
        "ALTER TABLE tasks ADD COLUMN result_integrity TEXT NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE ai_consent_audit ADD COLUMN authorization_source TEXT "
        "NOT NULL DEFAULT 'legacy'",
        """
        CREATE TABLE output_roots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            is_default INTEGER NOT NULL CHECK(is_default IN (0, 1)),
            is_current INTEGER NOT NULL CHECK(is_current IN (0, 1)),
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """,
        "CREATE UNIQUE INDEX idx_output_roots_current ON output_roots(is_current) "
        "WHERE is_current = 1",
        """
        CREATE TABLE monthly_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            year INTEGER NOT NULL CHECK(year BETWEEN 2000 AND 9999),
            month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
            job_id TEXT NOT NULL REFERENCES tasks(job_id) ON DELETE CASCADE,
            contract_version TEXT NOT NULL,
            snapshot_format TEXT NOT NULL,
            path TEXT NOT NULL,
            size INTEGER NOT NULL CHECK(size >= 0),
            sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id)
        )
        """,
        "CREATE INDEX idx_monthly_snapshots_period "
        "ON monthly_snapshots(module_id, year, month, status)",
        """
        CREATE TABLE monthly_slots (
            module_id TEXT NOT NULL,
            year INTEGER NOT NULL CHECK(year BETWEEN 2000 AND 9999),
            month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
            official_job_id TEXT NOT NULL REFERENCES tasks(job_id),
            snapshot_id TEXT NOT NULL REFERENCES monthly_snapshots(snapshot_id),
            committed_at TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            PRIMARY KEY(module_id, year, month)
        )
        """,
        """
        CREATE TABLE rollup_transactions (
            transaction_id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL,
            year INTEGER NOT NULL CHECK(year BETWEEN 2000 AND 9999),
            candidate_month INTEGER NOT NULL CHECK(candidate_month BETWEEN 1 AND 12),
            candidate_job_id TEXT NOT NULL REFERENCES tasks(job_id),
            old_job_id TEXT REFERENCES tasks(job_id),
            state TEXT NOT NULL,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            committed_at TEXT
        )
        """,
        "CREATE INDEX idx_rollup_transactions_candidate "
        "ON rollup_transactions(candidate_job_id, state)",
        """
        CREATE TABLE rollup_transaction_items (
            transaction_id TEXT NOT NULL
                REFERENCES rollup_transactions(transaction_id) ON DELETE CASCADE,
            target_month INTEGER NOT NULL CHECK(target_month BETWEEN 1 AND 12),
            official_job_id TEXT REFERENCES tasks(job_id),
            staged_path TEXT,
            output_manifest_sha256 TEXT,
            state TEXT NOT NULL,
            error_code TEXT,
            error_message TEXT,
            PRIMARY KEY(transaction_id, target_month)
        )
        """,
        """
        CREATE TABLE confirmation_drafts (
            job_id TEXT PRIMARY KEY REFERENCES tasks(job_id) ON DELETE CASCADE,
            answers_json TEXT NOT NULL,
            learning_enabled INTEGER NOT NULL CHECK(learning_enabled IN (0, 1)),
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE learning_evidence (
            evidence_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES tasks(job_id) ON DELETE CASCADE,
            module_id TEXT NOT NULL,
            year INTEGER NOT NULL CHECK(year BETWEEN 2000 AND 9999),
            month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
            confirmation_id TEXT NOT NULL,
            learning_key TEXT NOT NULL,
            field TEXT NOT NULL,
            context_json TEXT NOT NULL,
            context_levels_json TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            candidate_label TEXT NOT NULL,
            base_suggestion_id TEXT,
            weight INTEGER NOT NULL DEFAULT 1 CHECK(weight > 0),
            active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
            created_at TEXT NOT NULL,
            activated_at TEXT,
            revoked_at TEXT,
            revoked_reason TEXT,
            UNIQUE(job_id, confirmation_id)
        )
        """,
        "CREATE INDEX idx_learning_match ON learning_evidence(module_id, learning_key, active)",
        """
        CREATE TABLE learning_actions (
            action_id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            module_id TEXT NOT NULL,
            learning_key TEXT,
            evidence_id TEXT,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE credential_revisions (
            provider_id TEXT PRIMARY KEY,
            revision TEXT NOT NULL,
            changed_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE credential_verifications (
            provider_id TEXT NOT NULL,
            base_url TEXT NOT NULL,
            model TEXT NOT NULL,
            credential_revision TEXT NOT NULL,
            verified_at TEXT NOT NULL,
            PRIMARY KEY(provider_id, base_url, model, credential_revision)
        )
        """,
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

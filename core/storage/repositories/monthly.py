"""Framework-owned monthly slots, snapshots and atomic rollup transactions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from core.contracts.result import OutputArtifact
from core.storage.database import Database


class MonthlyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def register_snapshot(
        self,
        *,
        module_id: str,
        year: int,
        month: int,
        job_id: str,
        contract_version: str,
        snapshot_format: str,
        path: Path,
        size: int,
        sha256: str,
    ) -> str:
        _validate_period(year, month)
        if size < 0 or len(sha256) != 64:
            raise ValueError("invalid monthly snapshot integrity metadata")
        snapshot_id = uuid4().hex
        self.database.execute(
            "INSERT INTO monthly_snapshots("
            "snapshot_id, module_id, year, month, job_id, contract_version, "
            "snapshot_format, path, size, sha256, status, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)",
            (
                snapshot_id,
                module_id,
                year,
                month,
                job_id,
                contract_version,
                snapshot_format,
                str(path),
                size,
                sha256.lower(),
                _now(),
            ),
        )
        return snapshot_id

    def get_slot(self, module_id: str, year: int, month: int) -> dict[str, object] | None:
        row = self.database.connection.execute(
            "SELECT monthly_slots.*, tasks.task_name, tasks.result_path, "
            "tasks.result_integrity FROM monthly_slots "
            "JOIN tasks ON tasks.job_id = monthly_slots.official_job_id "
            "WHERE monthly_slots.module_id = ? AND year = ? AND month = ?",
            (module_id, year, month),
        ).fetchone()
        return None if row is None else dict(row)

    def get_snapshot_for_job(self, job_id: str) -> dict[str, object] | None:
        row = self.database.connection.execute(
            "SELECT * FROM monthly_snapshots WHERE job_id = ?", (job_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def list_year(self, module_id: str, year: int) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT monthly_slots.*, tasks.task_name, tasks.result_path, "
            "tasks.result_integrity FROM monthly_slots "
            "JOIN tasks ON tasks.job_id = monthly_slots.official_job_id "
            "WHERE monthly_slots.module_id = ? AND year = ? ORDER BY month",
            (module_id, year),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_official_snapshots(
        self, module_id: str, year: int, through_month: int
    ) -> list[dict[str, object]]:
        _validate_period(year, through_month)
        rows = self.database.connection.execute(
            "SELECT monthly_snapshots.* FROM monthly_slots "
            "JOIN monthly_snapshots USING(snapshot_id) "
            "WHERE monthly_slots.module_id = ? AND monthly_slots.year = ? "
            "AND monthly_slots.month <= ? ORDER BY monthly_slots.month",
            (module_id, year, through_month),
        ).fetchall()
        return [dict(row) for row in rows]

    def begin_transaction(
        self,
        *,
        module_id: str,
        year: int,
        candidate_month: int,
        candidate_job_id: str,
        affected_months: list[int],
    ) -> str:
        _validate_period(year, candidate_month)
        if not affected_months or affected_months != sorted(set(affected_months)):
            raise ValueError("affected months must be unique and ordered")
        if any(month < candidate_month or month > 12 for month in affected_months):
            raise ValueError("affected month is outside transaction range")
        old = self.get_slot(module_id, year, candidate_month)
        transaction_id = uuid4().hex
        now = _now()
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO rollup_transactions("
                "transaction_id, module_id, year, candidate_month, candidate_job_id, "
                "old_job_id, state, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, 'preparing', ?, ?)",
                (
                    transaction_id,
                    module_id,
                    year,
                    candidate_month,
                    candidate_job_id,
                    None if old is None else old["official_job_id"],
                    now,
                    now,
                ),
            )
            for month in affected_months:
                slot = self.get_slot(module_id, year, month)
                self.database.connection.execute(
                    "INSERT INTO rollup_transaction_items("
                    "transaction_id, target_month, official_job_id, state"
                    ") VALUES (?, ?, ?, 'pending')",
                    (
                        transaction_id,
                        month,
                        candidate_job_id
                        if month == candidate_month
                        else (None if slot is None else slot["official_job_id"]),
                    ),
                )
        return transaction_id

    def set_transaction_state(
        self,
        transaction_id: str,
        state: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if state not in {"preparing", "rendering", "validated", "failed"}:
            raise ValueError("invalid mutable transaction state")
        self.database.execute(
            "UPDATE rollup_transactions SET state = ?, error_code = ?, "
            "error_message = ?, updated_at = ? WHERE transaction_id = ?",
            (state, error_code, error_message, _now(), transaction_id),
        )

    def validate_item(
        self,
        transaction_id: str,
        target_month: int,
        *,
        staged_path: Path,
        manifest_sha256: str,
    ) -> None:
        if not 1 <= target_month <= 12 or len(manifest_sha256) != 64:
            raise ValueError("invalid rollup item metadata")
        self.database.execute(
            "UPDATE rollup_transaction_items SET state = 'validated', staged_path = ?, "
            "output_manifest_sha256 = ?, error_code = NULL, error_message = NULL "
            "WHERE transaction_id = ? AND target_month = ?",
            (str(staged_path), manifest_sha256.lower(), transaction_id, target_month),
        )

    def fail_item(
        self,
        transaction_id: str,
        target_month: int,
        error_code: str,
        error_message: str,
    ) -> None:
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE rollup_transaction_items SET state = 'failed', error_code = ?, "
                "error_message = ? WHERE transaction_id = ? AND target_month = ?",
                (error_code, error_message, transaction_id, target_month),
            )
            self.database.connection.execute(
                "UPDATE rollup_transactions SET state = 'failed', error_code = ?, "
                "error_message = ?, updated_at = ? WHERE transaction_id = ?",
                (error_code, error_message, _now(), transaction_id),
            )

    def commit(
        self,
        transaction_id: str,
        *,
        snapshot_by_month: dict[int, str],
        outputs_by_job: dict[str, list[OutputArtifact]],
        activate_learning_job: str | None,
        revoke_learning_job: str | None = None,
        remove_slot: tuple[str, int, int] | None = None,
    ) -> None:
        """Atomically switch all official slots after every output is validated."""

        connection = self.database.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            transaction = connection.execute(
                "SELECT * FROM rollup_transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if transaction is None or transaction["state"] not in {
                "rendering",
                "validated",
            }:
                raise ValueError("rollup transaction is not ready to commit")
            items = connection.execute(
                "SELECT * FROM rollup_transaction_items WHERE transaction_id = ? "
                "ORDER BY target_month",
                (transaction_id,),
            ).fetchall()
            if not items or any(item["state"] != "validated" for item in items):
                raise ValueError("all rollup transaction items must be validated")
            item_months = {int(item["target_month"]) for item in items}
            if set(snapshot_by_month) != item_months:
                raise ValueError("snapshot mapping does not match transaction items")
            committed_at = _now()
            for item in items:
                month = int(item["target_month"])
                job_id = str(item["official_job_id"])
                snapshot_id = snapshot_by_month[month]
                snapshot = connection.execute(
                    "SELECT module_id, year, month, job_id FROM monthly_snapshots "
                    "WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if (
                    snapshot is None
                    or snapshot["module_id"] != transaction["module_id"]
                    or snapshot["year"] != transaction["year"]
                    or snapshot["month"] != month
                    or snapshot["job_id"] != job_id
                ):
                    raise ValueError("snapshot identity does not match transaction item")
                connection.execute(
                    "INSERT INTO monthly_slots("
                    "module_id, year, month, official_job_id, snapshot_id, committed_at, "
                    "transaction_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(module_id, year, month) DO UPDATE SET "
                    "official_job_id=excluded.official_job_id, snapshot_id=excluded.snapshot_id, "
                    "committed_at=excluded.committed_at, transaction_id=excluded.transaction_id",
                    (
                        transaction["module_id"],
                        transaction["year"],
                        month,
                        job_id,
                        snapshot_id,
                        committed_at,
                        transaction_id,
                    ),
                )
                connection.execute(
                    "UPDATE monthly_snapshots SET status = 'official' WHERE snapshot_id = ?",
                    (snapshot_id,),
                )
            expected_jobs = {str(item["official_job_id"]) for item in items}
            if set(outputs_by_job) != expected_jobs:
                raise ValueError("output mapping does not match transaction jobs")
            for job_id, outputs in outputs_by_job.items():
                connection.execute("DELETE FROM outputs WHERE job_id = ?", (job_id,))
                connection.executemany(
                    "INSERT INTO outputs(job_id, artifact_type, path, label) "
                    "VALUES (?, ?, ?, ?)",
                    [(job_id, item.type, item.path, item.label) for item in outputs],
                )
                connection.execute(
                    "UPDATE tasks SET result_integrity = 'ok' WHERE job_id = ?", (job_id,)
                )
            if revoke_learning_job is not None:
                connection.execute(
                    "UPDATE learning_evidence SET active = 0, revoked_at = ?, "
                    "revoked_reason = 'official task replaced' "
                    "WHERE job_id = ? AND active = 1",
                    (committed_at, revoke_learning_job),
                )
            if activate_learning_job is not None:
                connection.execute(
                    "UPDATE learning_evidence SET active = 1, activated_at = ?, "
                    "revoked_at = NULL, revoked_reason = NULL "
                    "WHERE job_id = ? AND active = 0 AND revoked_at IS NULL",
                    (committed_at, activate_learning_job),
                )
            if remove_slot is not None:
                remove_module, remove_year, remove_month = remove_slot
                removed = connection.execute(
                    "SELECT snapshot_id FROM monthly_slots WHERE module_id = ? "
                    "AND year = ? AND month = ?",
                    (remove_module, remove_year, remove_month),
                ).fetchone()
                connection.execute(
                    "DELETE FROM monthly_slots WHERE module_id = ? AND year = ? AND month = ?",
                    (remove_module, remove_year, remove_month),
                )
                if removed is not None:
                    connection.execute(
                        "UPDATE monthly_snapshots SET status = 'revoked' "
                        "WHERE snapshot_id = ?",
                        (removed["snapshot_id"],),
                    )
            connection.execute(
                "UPDATE rollup_transactions SET state = 'committed', committed_at = ?, "
                "updated_at = ? WHERE transaction_id = ?",
                (committed_at, committed_at, transaction_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def remove_official_without_later(
        self, module_id: str, year: int, month: int, job_id: str
    ) -> None:
        _validate_period(year, month)
        with self.database.connection:
            later = self.database.connection.execute(
                "SELECT COUNT(*) FROM monthly_slots WHERE module_id = ? AND year = ? "
                "AND month > ?",
                (module_id, year, month),
            ).fetchone()[0]
            if later:
                raise ValueError("later official months must be rerendered before removal")
            slot = self.database.connection.execute(
                "SELECT snapshot_id, official_job_id FROM monthly_slots "
                "WHERE module_id = ? AND year = ? AND month = ?",
                (module_id, year, month),
            ).fetchone()
            if slot is None or slot["official_job_id"] != job_id:
                raise ValueError("official monthly slot changed before removal")
            now = _now()
            self.database.connection.execute(
                "DELETE FROM monthly_slots WHERE module_id = ? AND year = ? AND month = ?",
                (module_id, year, month),
            )
            self.database.connection.execute(
                "UPDATE monthly_snapshots SET status = 'revoked' WHERE snapshot_id = ?",
                (slot["snapshot_id"],),
            )
            self.database.connection.execute(
                "UPDATE learning_evidence SET active = 0, revoked_at = ?, "
                "revoked_reason = 'official task removed' "
                "WHERE job_id = ? AND active = 1",
                (now, job_id),
            )

    def list_interrupted(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM rollup_transactions WHERE state IN "
            "('preparing', 'rendering', 'validated') ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def recover_official_slot(
        self,
        *,
        module_id: str,
        year: int,
        month: int,
        job_id: str,
        snapshot_id: str,
        committed_at: str,
        transaction_id: str,
    ) -> None:
        _validate_period(year, month)
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE monthly_snapshots SET status = 'official' WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            self.database.connection.execute(
                "INSERT INTO monthly_slots("
            "module_id, year, month, official_job_id, snapshot_id, committed_at, transaction_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(module_id, year, month) "
            "DO UPDATE SET official_job_id=excluded.official_job_id, "
            "snapshot_id=excluded.snapshot_id, committed_at=excluded.committed_at, "
            "transaction_id=excluded.transaction_id",
                (module_id, year, month, job_id, snapshot_id, committed_at, transaction_id),
            )

    def active_months(self, module_id: str, year: int) -> set[int]:
        rows = self.database.connection.execute(
            "SELECT DISTINCT rollup_transaction_items.target_month "
            "FROM rollup_transactions JOIN rollup_transaction_items USING(transaction_id) "
            "WHERE rollup_transactions.module_id = ? AND rollup_transactions.year = ? "
            "AND rollup_transactions.state IN ('preparing', 'rendering', 'validated')",
            (module_id, year),
        ).fetchall()
        return {int(row[0]) for row in rows}


def _validate_period(year: int, month: int) -> None:
    if not 2000 <= year <= 9999 or not 1 <= month <= 12:
        raise ValueError("invalid monthly period")


def _now() -> str:
    return datetime.now().astimezone().isoformat()

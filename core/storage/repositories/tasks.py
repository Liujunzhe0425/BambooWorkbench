from datetime import datetime

from core.contracts.result import OutputArtifact
from core.storage.database import Database


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        job_id: str,
        module_id: str,
        status: str,
        created_at: str,
        parent_job_id: str | None = None,
        *,
        task_name: str | None = None,
        period_year: int | None = None,
        period_month: int | None = None,
        learning_enabled: bool = True,
        candidate_for_job_id: str | None = None,
        output_root_id: int | None = None,
    ) -> None:
        self.database.execute(
            "INSERT INTO tasks("
            "job_id, module_id, status, created_at, updated_at, parent_job_id, "
            "task_name, period_year, period_month, learning_enabled, "
            "candidate_for_job_id, output_root_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                module_id,
                status,
                created_at,
                created_at,
                parent_job_id,
                task_name,
                period_year,
                period_month,
                int(learning_enabled),
                candidate_for_job_id,
                output_root_id,
            ),
        )

    def update_status(
        self,
        job_id: str,
        status: str,
        error: str | None = None,
        result_path: str | None = None,
    ) -> None:
        updated_at = datetime.now().astimezone().isoformat()
        self.database.execute(
            "UPDATE tasks SET status = ?, updated_at = ?, "
            "error = COALESCE(?, error), result_path = COALESCE(?, result_path) "
            "WHERE job_id = ?",
            (status, updated_at, error, result_path, job_id),
        )

    def get(self, job_id: str) -> dict[str, object]:
        row = self.database.connection.execute(
            "SELECT * FROM tasks WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def exists(self, job_id: str) -> bool:
        return bool(
            self.database.scalar("SELECT COUNT(*) FROM tasks WHERE job_id = ?", (job_id,))
        )

    def get_number(self, job_id: str) -> int:
        row = self.database.connection.execute(
            "SELECT task_number FROM ("
            "SELECT job_id, ROW_NUMBER() OVER (ORDER BY created_at, rowid) AS task_number "
            "FROM tasks"
            ") WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return int(row["task_number"])

    def list_recent(self, limit: int = 20) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM ("
            "SELECT ROW_NUMBER() OVER (ORDER BY created_at, rowid) AS task_number, tasks.* "
            "FROM tasks"
            ") ORDER BY created_at DESC, task_number DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_by_status(self, statuses: tuple[str, ...]) -> list[dict[str, object]]:
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        rows = self.database.connection.execute(
            f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY created_at",
            statuses,
        ).fetchall()
        return [dict(row) for row in rows]

    def list_waiting_confirmation(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT tasks.*, COUNT(confirmations.confirmation_id) AS confirmation_count "
            "FROM tasks LEFT JOIN confirmations USING(job_id) "
            "WHERE tasks.status = 'waiting_confirmation' "
            "GROUP BY tasks.job_id ORDER BY tasks.created_at DESC, tasks.rowid DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def set_period_metadata(
        self,
        job_id: str,
        *,
        task_name: str,
        year: int,
        month: int,
        learning_enabled: bool,
        candidate_for_job_id: str | None = None,
        output_root_id: int | None = None,
    ) -> None:
        if not 2000 <= year <= 9999 or not 1 <= month <= 12:
            raise ValueError("invalid task period")
        if not task_name.strip():
            raise ValueError("task name must not be empty")
        self.database.execute(
            "UPDATE tasks SET task_name = ?, period_year = ?, period_month = ?, "
            "learning_enabled = ?, candidate_for_job_id = ?, output_root_id = ? "
            "WHERE job_id = ?",
            (
                task_name.strip(),
                year,
                month,
                int(learning_enabled),
                candidate_for_job_id,
                output_root_id,
                job_id,
            ),
        )

    def set_result_integrity(self, job_id: str, integrity: str) -> None:
        if integrity not in {"unknown", "ok", "missing", "invalid", "conflict"}:
            raise ValueError("invalid result integrity state")
        self.database.execute(
            "UPDATE tasks SET result_integrity = ?, updated_at = ? WHERE job_id = ?",
            (integrity, datetime.now().astimezone().isoformat(), job_id),
        )

    def set_learning_enabled(self, job_id: str, enabled: bool) -> None:
        self.database.execute(
            "UPDATE tasks SET learning_enabled = ?, updated_at = ? WHERE job_id = ?",
            (int(enabled), datetime.now().astimezone().isoformat(), job_id),
        )

    def add_file(
        self,
        job_id: str,
        source_path: str,
        snapshot_path: str,
        fingerprint: str,
        status: str,
    ) -> None:
        self.database.execute(
            "INSERT INTO task_files("
            "job_id, source_path, snapshot_path, fingerprint, status"
            ") VALUES (?, ?, ?, ?, ?)",
            (job_id, source_path, snapshot_path, fingerprint, status),
        )

    def add_files(self, job_id: str, files: list[tuple[str, str, str, str]]) -> None:
        values = [(job_id, *file_record) for file_record in files]
        with self.database.connection:
            self.database.connection.executemany(
                "INSERT INTO task_files("
                "job_id, source_path, snapshot_path, fingerprint, status"
                ") VALUES (?, ?, ?, ?, ?)",
                values,
            )

    def list_files(self, job_id: str) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM task_files WHERE job_id = ? ORDER BY source_path", (job_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_outputs(self, job_id: str, outputs: list[OutputArtifact]) -> None:
        with self.database.connection:
            self.database.connection.execute("DELETE FROM outputs WHERE job_id = ?", (job_id,))
            self.database.connection.executemany(
                "INSERT INTO outputs(job_id, artifact_type, path, label) VALUES (?, ?, ?, ?)",
                [(job_id, output.type, output.path, output.label) for output in outputs],
            )

    def list_outputs(self, job_id: str) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM outputs WHERE job_id = ? ORDER BY rowid", (job_id,)
        ).fetchall()
        return [dict(row) for row in rows]

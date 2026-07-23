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
    ) -> None:
        self.database.execute(
            "INSERT INTO tasks("
            "job_id, module_id, status, created_at, updated_at, parent_job_id"
            ") VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, module_id, status, created_at, created_at, parent_job_id),
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

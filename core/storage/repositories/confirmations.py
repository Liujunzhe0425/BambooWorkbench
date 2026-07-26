import json
from datetime import datetime

from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.result import ConfirmationPrompt
from core.storage.database import Database


class ConfirmationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_prompts(self, job_id: str, prompts: list[ConfirmationPrompt]) -> None:
        values = [
            (
                job_id,
                prompt.confirmation_id,
                json.dumps(prompt.model_dump(mode="json"), ensure_ascii=False),
            )
            for prompt in prompts
        ]
        with self.database.connection:
            self.database.connection.executemany(
                "INSERT INTO confirmations(job_id, confirmation_id, original_prompt) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(job_id, confirmation_id) DO UPDATE SET "
                "original_prompt = excluded.original_prompt",
                values,
            )

    def save_answers(self, job_id: str, answers: list[ConfirmationAnswer]) -> None:
        if not answers:
            return
        answer_ids = {answer.confirmation_id for answer in answers}
        placeholders = ", ".join("?" for _ in answer_ids)
        rows = self.database.connection.execute(
            f"SELECT confirmation_id FROM confirmations "
            f"WHERE job_id = ? AND confirmation_id IN ({placeholders})",
            (job_id, *answer_ids),
        ).fetchall()
        stored_ids = {row["confirmation_id"] for row in rows}
        unknown_ids = answer_ids - stored_ids
        if unknown_ids:
            raise KeyError(f"unknown confirmations for {job_id}: {sorted(unknown_ids)}")

        answered_at = datetime.now().astimezone().isoformat()
        values = [
            (
                json.dumps(answer.model_dump(mode="json"), ensure_ascii=False),
                answered_at,
                job_id,
                answer.confirmation_id,
            )
            for answer in answers
        ]
        with self.database.connection:
            self.database.connection.executemany(
                "UPDATE confirmations SET answer = ?, answered_at = ? "
                "WHERE job_id = ? AND confirmation_id = ?",
                values,
            )

    def replace_answers(self, job_id: str, answers: list[ConfirmationAnswer]) -> None:
        answer_ids = [answer.confirmation_id for answer in answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("duplicate confirmation answer IDs")
        rows = self.database.connection.execute(
            "SELECT confirmation_id FROM confirmations WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        stored_ids = {str(row["confirmation_id"]) for row in rows}
        unknown_ids = set(answer_ids) - stored_ids
        if unknown_ids:
            raise KeyError(f"unknown confirmations for {job_id}: {sorted(unknown_ids)}")

        answered_at = datetime.now().astimezone().isoformat()
        values = [
            (
                json.dumps(answer.model_dump(mode="json"), ensure_ascii=False),
                answered_at,
                job_id,
                answer.confirmation_id,
            )
            for answer in answers
        ]
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE confirmations SET answer = NULL, answered_at = NULL WHERE job_id = ?",
                (job_id,),
            )
            self.database.connection.executemany(
                "UPDATE confirmations SET answer = ?, answered_at = ? "
                "WHERE job_id = ? AND confirmation_id = ?",
                values,
            )

    def list_for_job(self, job_id: str) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM confirmations WHERE job_id = ? ORDER BY confirmation_id", (job_id,)
        ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            record["original_prompt"] = json.loads(str(record["original_prompt"]))
            if record["answer"] is not None:
                record["answer"] = json.loads(str(record["answer"]))
        return records

    def save_draft(
        self,
        job_id: str,
        answers: list[ConfirmationAnswer],
        *,
        learning_enabled: bool,
    ) -> None:
        answer_ids = [answer.confirmation_id for answer in answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("duplicate confirmation answer IDs")
        known = {
            str(row["confirmation_id"])
            for row in self.database.connection.execute(
                "SELECT confirmation_id FROM confirmations WHERE job_id = ?", (job_id,)
            ).fetchall()
        }
        unknown = set(answer_ids) - known
        if unknown:
            raise KeyError(f"unknown confirmations for {job_id}: {sorted(unknown)}")
        payload = json.dumps(
            [answer.model_dump(mode="json") for answer in answers],
            ensure_ascii=False,
            sort_keys=True,
        )
        self.database.execute(
            "INSERT INTO confirmation_drafts("
            "job_id, answers_json, learning_enabled, updated_at"
            ") VALUES (?, ?, ?, ?) ON CONFLICT(job_id) DO UPDATE SET "
            "answers_json=excluded.answers_json, "
            "learning_enabled=excluded.learning_enabled, updated_at=excluded.updated_at",
            (
                job_id,
                payload,
                int(learning_enabled),
                datetime.now().astimezone().isoformat(),
            ),
        )

    def load_draft(self, job_id: str) -> dict[str, object] | None:
        row = self.database.connection.execute(
            "SELECT * FROM confirmation_drafts WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "job_id": str(row["job_id"]),
            "answers": [
                ConfirmationAnswer.model_validate(item)
                for item in json.loads(str(row["answers_json"]))
            ],
            "learning_enabled": bool(row["learning_enabled"]),
            "updated_at": str(row["updated_at"]),
        }

    def delete_draft(self, job_id: str) -> None:
        self.database.execute("DELETE FROM confirmation_drafts WHERE job_id = ?", (job_id,))

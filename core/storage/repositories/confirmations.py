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

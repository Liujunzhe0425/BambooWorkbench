import os
import re
import tempfile
from pathlib import Path

from core.contracts.confirmation import ConfirmationAnswer, ConfirmationBundle
from core.contracts.result import ConfirmationPrompt
from core.platform.paths import AppPaths
from core.storage.repositories.confirmations import ConfirmationRepository

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{6,64}$")


def _atomic_write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class ConfirmationService:
    def __init__(self, paths: AppPaths, repository: ConfirmationRepository) -> None:
        self.paths = paths
        self.repository = repository

    def submit(self, job_id: str, answers: list[ConfirmationAnswer]) -> Path:
        if not _JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("invalid job ID")
        task_dir = self.paths.tasks / job_id
        if not task_dir.is_dir():
            raise ValueError(f"task directory does not exist for {job_id}")

        records = self.repository.list_for_job(job_id)
        if not records:
            raise ValueError(f"no stored confirmation prompts for {job_id}")
        prompts = [
            ConfirmationPrompt.model_validate(record["original_prompt"])
            for record in records
        ]
        answer_ids = [answer.confirmation_id for answer in answers]
        supplied = set(answer_ids)
        if len(supplied) != len(answer_ids):
            raise ValueError("duplicate confirmation answer IDs")
        known = {prompt.confirmation_id for prompt in prompts}
        unknown = supplied - known
        if unknown:
            raise ValueError(f"unknown confirmation answer IDs: {sorted(unknown)}")
        required = {prompt.confirmation_id for prompt in prompts if prompt.blocking}
        missing = required - supplied
        if missing:
            raise ValueError(f"missing blocking confirmations: {sorted(missing)}")

        bundle = ConfirmationBundle(job_id=job_id, answers=answers)
        path = task_dir / "confirmation.json"
        _atomic_write_text(path, bundle.model_dump_json(indent=2))
        self.repository.save_answers(job_id, answers)
        return path

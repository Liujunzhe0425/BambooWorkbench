"""Non-secret credential revision and connection-verification state."""

from datetime import datetime
from uuid import uuid4

from core.storage.database import Database


class CredentialStateRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def rotate_revision(self, provider_id: str) -> str:
        revision = uuid4().hex
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO credential_revisions(provider_id, revision, changed_at) "
                "VALUES (?, ?, ?) ON CONFLICT(provider_id) DO UPDATE SET "
                "revision=excluded.revision, changed_at=excluded.changed_at",
                (provider_id, revision, _now()),
            )
            self.database.connection.execute(
                "DELETE FROM credential_verifications WHERE provider_id = ?", (provider_id,)
            )
        return revision

    def revision(self, provider_id: str) -> str | None:
        value = self.database.scalar(
            "SELECT revision FROM credential_revisions WHERE provider_id = ?", (provider_id,)
        )
        return None if value is None else str(value)

    def mark_verified(self, provider_id: str, base_url: str, model: str) -> None:
        revision = self.revision(provider_id)
        if revision is None:
            raise ValueError("credential revision is not initialized")
        self.database.execute(
            "INSERT INTO credential_verifications("
            "provider_id, base_url, model, credential_revision, verified_at"
            ") VALUES (?, ?, ?, ?, ?) ON CONFLICT DO UPDATE SET verified_at=excluded.verified_at",
            (provider_id, base_url.strip(), model.strip(), revision, _now()),
        )

    def is_verified(self, provider_id: str, base_url: str, model: str) -> bool:
        revision = self.revision(provider_id)
        if revision is None:
            return False
        return bool(
            self.database.scalar(
                "SELECT COUNT(*) FROM credential_verifications WHERE provider_id = ? "
                "AND base_url = ? AND model = ? AND credential_revision = ?",
                (provider_id, base_url.strip(), model.strip(), revision),
            )
        )

    def invalidate(self, provider_id: str) -> None:
        self.rotate_revision(provider_id)


def _now() -> str:
    return datetime.now().astimezone().isoformat()

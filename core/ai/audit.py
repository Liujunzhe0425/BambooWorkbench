import json
from dataclasses import dataclass

from core.storage.database import Database


@dataclass(frozen=True)
class ConsentDecision:
    task_id: str
    module_id: str
    provider_id: str
    allowed: bool
    data_categories: tuple[str, ...]
    decided_at: str
    authorization_source: str = "legacy"


class ConsentAuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(self, decision: ConsentDecision) -> None:
        self.database.execute(
            "INSERT INTO ai_consent_audit("
            "task_id,module_id,provider_id,allowed,data_categories_json,decided_at,"
            "authorization_source) VALUES(?,?,?,?,?,?,?)",
            (
                decision.task_id,
                decision.module_id,
                decision.provider_id,
                int(decision.allowed),
                json.dumps(decision.data_categories, ensure_ascii=False),
                decision.decided_at,
                decision.authorization_source,
            ),
        )

    def list_for_task(self, task_id: str) -> list[ConsentDecision]:
        rows = self.database.query_all(
            "SELECT * FROM ai_consent_audit WHERE task_id=? ORDER BY id", (task_id,)
        )
        return [
            ConsentDecision(
                task_id=str(row["task_id"]),
                module_id=str(row["module_id"]),
                provider_id=str(row["provider_id"]),
                allowed=bool(row["allowed"]),
                data_categories=tuple(json.loads(str(row["data_categories_json"]))),
                decided_at=str(row["decided_at"]),
                authorization_source=str(row["authorization_source"]),
            )
            for row in rows
        ]

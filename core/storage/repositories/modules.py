from core.storage.database import Database


class ModuleRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        module_id: str,
        version: str,
        path: str,
        is_mock: bool,
        health: str,
    ) -> None:
        self.database.execute(
            "INSERT INTO modules(module_id, version, path, is_mock, health) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(module_id) DO UPDATE SET "
            "version = excluded.version, path = excluded.path, "
            "is_mock = excluded.is_mock, health = excluded.health",
            (module_id, version, path, int(is_mock), health),
        )

    def list_all(self) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM modules ORDER BY module_id"
        ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            record["is_mock"] = bool(record["is_mock"])
        return records

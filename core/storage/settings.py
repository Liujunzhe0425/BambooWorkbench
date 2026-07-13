from core.storage.database import Database


class SettingsStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def set(self, key: str, value: str) -> None:
        self.database.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self.database.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return default if value is None else str(value)

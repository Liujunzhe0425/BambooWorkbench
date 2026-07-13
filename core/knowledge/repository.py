from core.knowledge.models import (
    ALLOWED_NAMESPACES,
    SOURCE_PRIORITY,
    KnowledgeRecord,
    KnowledgeSourceKind,
)
from core.storage.database import Database


class KnowledgeRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(self, record: KnowledgeRecord) -> None:
        self.database.execute(
            "INSERT INTO knowledge_records("
            "record_id,namespace,title,content,source_kind,enabled,source_path"
            ") VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(record_id) DO UPDATE SET "
            "namespace=excluded.namespace,title=excluded.title,content=excluded.content,"
            "source_kind=excluded.source_kind,enabled=excluded.enabled,"
            "source_path=excluded.source_path",
            (
                record.record_id,
                record.namespace,
                record.title,
                record.content,
                record.source_kind.value,
                int(record.enabled),
                record.source_path,
            ),
        )

    def set_enabled(self, record_id: str, enabled: bool) -> None:
        cursor = self.database.execute(
            "UPDATE knowledge_records SET enabled=? WHERE record_id=?",
            (int(enabled), record_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(record_id)

    def list_records(self, namespace: str | None = None) -> list[KnowledgeRecord]:
        if namespace is not None and namespace not in ALLOWED_NAMESPACES:
            raise ValueError(f"unsupported knowledge namespace: {namespace}")
        if namespace is None:
            rows = self.database.query_all("SELECT * FROM knowledge_records")
        else:
            rows = self.database.query_all(
                "SELECT * FROM knowledge_records WHERE namespace=?", (namespace,)
            )
        return sorted((self._from_row(row) for row in rows), key=self._sort_key)

    def search(self, namespace: str, query: str) -> list[KnowledgeRecord]:
        if namespace not in ALLOWED_NAMESPACES:
            raise ValueError(f"unsupported knowledge namespace: {namespace}")
        pattern = f"%{query.strip()}%"
        if namespace == "shared":
            rows = self.database.query_all(
                "SELECT * FROM knowledge_records "
                "WHERE enabled=1 AND namespace='shared' "
                "AND (title LIKE ? OR content LIKE ?)",
                (pattern, pattern),
            )
        else:
            rows = self.database.query_all(
                "SELECT * FROM knowledge_records "
                "WHERE enabled=1 AND namespace IN ('shared', ?) "
                "AND (title LIKE ? OR content LIKE ?)",
                (namespace, pattern, pattern),
            )
        return sorted((self._from_row(row) for row in rows), key=self._sort_key)

    @staticmethod
    def _from_row(row: object) -> KnowledgeRecord:
        return KnowledgeRecord(
            record_id=str(row["record_id"]),
            namespace=str(row["namespace"]),
            title=str(row["title"]),
            content=str(row["content"]),
            source_kind=KnowledgeSourceKind(str(row["source_kind"])),
            enabled=bool(row["enabled"]),
            source_path=None if row["source_path"] is None else str(row["source_path"]),
        )

    @staticmethod
    def _sort_key(record: KnowledgeRecord) -> tuple[int, str, str]:
        return SOURCE_PRIORITY[record.source_kind], record.title, record.record_id

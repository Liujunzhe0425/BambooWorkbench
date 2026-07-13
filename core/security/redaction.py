import re
from dataclasses import dataclass
from typing import Any

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "customer_name",
    "email",
    "operator_name",
    "phone",
    "token",
}
WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
UNC_PATH = re.compile(r"^\\\\[^\\]+\\")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE = re.compile(r"^(?:\+?86[- ]?)?1\d{10}$")


@dataclass(frozen=True)
class RedactionPreview:
    payload: Any
    categories: tuple[str, ...]


class RedactionService:
    def redact(self, value: Any) -> RedactionPreview:
        categories: set[str] = set()

        def visit(item: Any, key: str | None = None) -> Any:
            normalized_key = key.lower().replace("-", "_") if key else None
            if normalized_key in SENSITIVE_KEYS:
                categories.add("personal_field")
                return "[REDACTED]"
            if isinstance(item, str):
                if WINDOWS_PATH.match(item) or UNC_PATH.match(item):
                    categories.add("local_path")
                    return "[LOCAL_PATH]"
                if EMAIL.match(item) or PHONE.match(item):
                    categories.add("personal_value")
                    return "[REDACTED]"
            if isinstance(item, dict):
                return {str(k): visit(v, str(k)) for k, v in item.items()}
            if isinstance(item, list):
                return [visit(v) for v in item]
            if isinstance(item, tuple):
                return [visit(v) for v in item]
            return item

        return RedactionPreview(visit(value), tuple(sorted(categories)))

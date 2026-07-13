from enum import StrEnum


class ModuleId(StrEnum):
    MOISTURE = "moisture"
    BOILING = "boiling"
    AFTER_SALES = "after_sales"


class TaskStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NEEDS_CONFIRMATION = "needs_confirmation"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

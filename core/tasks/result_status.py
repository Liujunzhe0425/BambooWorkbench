"""Framework-owned task status semantics.

Business anomalies, review requests and AI degradation describe the contents of a
successful run.  They are deliberately not treated as file-processing failures.
"""

from core.contracts.enums import TaskStatus
from core.contracts.result import ModuleResult


def effective_task_status(result: ModuleResult) -> TaskStatus:
    """Return the host-level terminal status without mutating module evidence."""

    if result.status in {
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.NEEDS_CONFIRMATION,
    }:
        return result.status

    failed_files = max(
        result.summary.failed_count,
        sum(item.status is TaskStatus.FAILED for item in result.file_results),
    )
    if failed_files <= 0:
        return TaskStatus.SUCCESS

    successful_files = sum(
        item.status not in {TaskStatus.FAILED, TaskStatus.CANCELLED}
        for item in result.file_results
    )
    if successful_files or result.summary.processed_count > failed_files:
        return TaskStatus.PARTIAL_SUCCESS
    return TaskStatus.FAILED


def normalized_result(result: ModuleResult) -> ModuleResult:
    """Return a host-facing copy whose status follows the framework policy."""

    status = effective_task_status(result)
    if status is result.status:
        return result
    return result.model_copy(update={"status": status})

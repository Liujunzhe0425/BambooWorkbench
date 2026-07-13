from dataclasses import dataclass
from enum import StrEnum


class TaskLifecycleState(StrEnum):
    CREATED = "created"
    RUNNING_DRAFT = "running_draft"
    WAITING_CONFIRMATION = "waiting_confirmation"
    RUNNING_FINALIZE = "running_finalize"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidTaskTransition(ValueError):
    """Raised when a task attempts a lifecycle transition that is not allowed."""


_ALLOWED_TRANSITIONS: dict[TaskLifecycleState, frozenset[TaskLifecycleState]] = {
    TaskLifecycleState.CREATED: frozenset(
        {
            TaskLifecycleState.RUNNING_DRAFT,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.CANCELLED,
        }
    ),
    TaskLifecycleState.RUNNING_DRAFT: frozenset(
        {
            TaskLifecycleState.WAITING_CONFIRMATION,
            TaskLifecycleState.SUCCESS,
            TaskLifecycleState.PARTIAL_SUCCESS,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.CANCELLED,
        }
    ),
    TaskLifecycleState.WAITING_CONFIRMATION: frozenset(
        {
            TaskLifecycleState.RUNNING_FINALIZE,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.CANCELLED,
        }
    ),
    TaskLifecycleState.RUNNING_FINALIZE: frozenset(
        {
            TaskLifecycleState.SUCCESS,
            TaskLifecycleState.PARTIAL_SUCCESS,
            TaskLifecycleState.FAILED,
            TaskLifecycleState.CANCELLED,
        }
    ),
    TaskLifecycleState.SUCCESS: frozenset(),
    TaskLifecycleState.PARTIAL_SUCCESS: frozenset(),
    TaskLifecycleState.FAILED: frozenset(),
    TaskLifecycleState.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class TaskStateMachine:
    state: TaskLifecycleState = TaskLifecycleState.CREATED

    def ensure_transition(self, target: TaskLifecycleState) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTaskTransition(f"invalid task transition: {self.state} -> {target}")

    def transition(self, target: TaskLifecycleState) -> None:
        self.ensure_transition(target)
        self.state = target

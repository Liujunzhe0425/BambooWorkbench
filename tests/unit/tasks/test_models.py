import pytest

from core.tasks.models import InvalidTaskTransition, TaskLifecycleState, TaskStateMachine


def test_task_state_machine_enforces_draft_confirmation_finalize_lifecycle() -> None:
    machine = TaskStateMachine()

    machine.transition(TaskLifecycleState.RUNNING_DRAFT)
    machine.transition(TaskLifecycleState.WAITING_CONFIRMATION)
    machine.transition(TaskLifecycleState.RUNNING_FINALIZE)
    machine.transition(TaskLifecycleState.SUCCESS)

    assert machine.state is TaskLifecycleState.SUCCESS
    with pytest.raises(InvalidTaskTransition, match="success -> running_draft"):
        machine.transition(TaskLifecycleState.RUNNING_DRAFT)


def test_task_state_machine_allows_draft_terminal_outcomes() -> None:
    for terminal in (
        TaskLifecycleState.SUCCESS,
        TaskLifecycleState.PARTIAL_SUCCESS,
        TaskLifecycleState.FAILED,
        TaskLifecycleState.CANCELLED,
    ):
        machine = TaskStateMachine()
        machine.transition(TaskLifecycleState.RUNNING_DRAFT)

        machine.transition(terminal)

        assert machine.state is terminal


def test_task_state_machine_rejects_skipping_required_running_state() -> None:
    machine = TaskStateMachine()

    with pytest.raises(InvalidTaskTransition, match="created -> success"):
        machine.transition(TaskLifecycleState.SUCCESS)

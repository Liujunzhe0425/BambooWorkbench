import argparse
import ctypes
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from ctypes import wintypes
from pathlib import Path
from typing import NoReturn

if __package__:
    from .launcher import launcher_validation_error
else:
    from launcher import launcher_validation_error

HOST_SETUP_ERROR = 70
HOST_CHILD_START_ERROR = 71
HOST_UNSUPPORTED = 72
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


class JobSetupError(RuntimeError):
    pass


class _IOCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IOCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJob:
    def __init__(self, handle: int, kernel32: object) -> None:
        self.handle = handle
        self.kernel32 = kernel32


def create_contained_job() -> WindowsJob:
    if sys.platform != "win32":
        raise JobSetupError("Windows Job Objects are unavailable")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise JobSetupError(_windows_error("CreateJobObjectW"))

    assigned = False
    try:
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not configured:
            raise JobSetupError(_windows_error("SetInformationJobObject"))
        if not kernel32.AssignProcessToJobObject(handle, kernel32.GetCurrentProcess()):
            raise JobSetupError(_windows_error("AssignProcessToJobObject"))
        assigned = True
        return WindowsJob(int(handle), kernel32)
    finally:
        if not assigned:
            kernel32.CloseHandle(handle)


def run_host(
    launcher: Path,
    launcher_arguments: Sequence[str],
    *,
    job_factory: Callable[[], WindowsJob] = create_contained_job,
    child_runner: Callable[..., subprocess.CompletedProcess[object]] | None = None,
    host_exit: Callable[[int], NoReturn] | None = None,
) -> int:
    if host_exit is None:
        host_exit = terminate_current_process
    if child_runner is None:
        child_runner = _run_streaming_child
    launcher = launcher.resolve()
    validation_error = launcher_validation_error(launcher)
    if validation_error is not None:
        print(f"module host rejected launcher: {validation_error}", file=sys.stderr, flush=True)
        return HOST_CHILD_START_ERROR
    arguments = list(launcher_arguments)
    valid_self_check = arguments == ["self-check"]
    valid_run = (
        len(arguments) == 3
        and arguments[:2] == ["run", "--job"]
        and Path(arguments[2]).is_absolute()
    )
    valid_manage = (
        len(arguments) == 5
        and arguments[0] == "manage"
        and arguments[1] == "--request"
        and Path(arguments[2]).is_absolute()
        and arguments[3] == "--response"
        and Path(arguments[4]).is_absolute()
    )
    valid_rollup = (
        len(arguments) == 5
        and arguments[0] == "rollup"
        and arguments[1] == "--request"
        and Path(arguments[2]).is_absolute()
        and arguments[3] == "--response"
        and Path(arguments[4]).is_absolute()
    )
    if not valid_self_check and not valid_run and not valid_manage and not valid_rollup:
        print("module host rejected command", file=sys.stderr, flush=True)
        return HOST_CHILD_START_ERROR
    if sys.platform != "win32":
        print("module host requires Windows Job Object containment", file=sys.stderr, flush=True)
        return HOST_UNSUPPORTED

    try:
        _job = job_factory()
    except JobSetupError as exc:
        print(f"module host job setup failed: {exc}", file=sys.stderr, flush=True)
        return HOST_SETUP_ERROR

    system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    command_processor = str(system_root / "System32" / "cmd.exe")
    environment = os.environ.copy()
    environment["BAMBOO_HOST_LAUNCHER"] = str(launcher)
    references = ['"%BAMBOO_HOST_LAUNCHER%"']
    for index, argument in enumerate(arguments):
        name = f"BAMBOO_HOST_ARG_{index}"
        environment[name] = argument
        references.append(f'"%{name}%"')
    fixed_command = f'"{" ".join(references)}"'
    command = (
        f'{subprocess.list2cmdline([command_processor])} '
        f"/d /v:off /s /c {fixed_command}"
    )
    try:
        completed = child_runner(
            command,
            cwd=launcher.parent,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=environment,
        )
    except OSError as exc:
        print(f"module host child start failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        host_exit(HOST_CHILD_START_ERROR)
    _forward_child_output(completed)
    host_exit(completed.returncode)


def terminate_current_process(exit_code: int) -> NoReturn:
    sys.stdout.flush()
    sys.stderr.flush()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    if not kernel32.TerminateProcess(kernel32.GetCurrentProcess(), exit_code):
        raise JobSetupError(_windows_error("TerminateProcess"))
    raise RuntimeError("TerminateProcess unexpectedly returned")


def _forward_child_output(completed: subprocess.CompletedProcess[object]) -> None:
    stdout = completed.stdout
    stderr = completed.stderr
    if stdout:
        sys.stdout.buffer.write(stdout if isinstance(stdout, bytes) else stdout.encode())
        sys.stdout.buffer.flush()
    if stderr:
        sys.stderr.buffer.write(stderr if isinstance(stderr, bytes) else stderr.encode())
        sys.stderr.buffer.flush()


def _run_streaming_child(
    command: str,
    *,
    cwd: Path,
    check: bool,
    creationflags: int,
    env: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        env=env,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(
        target=_relay_lines, args=(process.stdout, sys.stdout.buffer), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_relay_lines, args=(process.stderr, sys.stderr.buffer), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    if check and return_code:
        raise subprocess.CalledProcessError(return_code, command)
    return subprocess.CompletedProcess(command, return_code)


def _relay_lines(source: object, destination: object) -> None:
    while line := source.readline():
        destination.write(line)
        destination.flush()


def _windows_error(operation: str) -> str:
    return f"{operation} failed with Windows error {ctypes.get_last_error()}"


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launcher", required=True, type=Path)
    parser.add_argument("command", choices=["self-check", "run", "manage", "rollup"])
    parser.add_argument("--job", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--response", type=Path)
    parsed = parser.parse_args(arguments)
    launcher_arguments = [parsed.command]
    if parsed.job is not None:
        launcher_arguments.extend(["--job", str(parsed.job.resolve())])
    if parsed.request is not None:
        launcher_arguments.extend(["--request", str(parsed.request.resolve())])
    if parsed.response is not None:
        launcher_arguments.extend(["--response", str(parsed.response.resolve())])
    return run_host(parsed.launcher, launcher_arguments)


if __name__ == "__main__":
    raise SystemExit(main())

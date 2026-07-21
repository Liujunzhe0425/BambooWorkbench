"""Verify that the frozen module emits strict UTF-8 line-delimited JSON."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) not in {3, 4}:
        print(
            "用法: verify_portable_runtime.py <运行程序> [模块启动脚本] <任务文件>",
            file=sys.stderr,
        )
        return 2

    runtime_exe = Path(sys.argv[1]).resolve()
    job_path = Path(sys.argv[-1]).resolve()
    if len(sys.argv) == 4:
        launcher = Path(sys.argv[2]).resolve()
        command = [
            str(runtime_exe),
            "--launcher",
            str(launcher),
            "run",
            "--job",
            str(job_path),
        ]
    else:
        command = [str(runtime_exe), "run", "--job", str(job_path)]
    completed = subprocess.run(
        command,
        capture_output=True,
        timeout=120,
        check=False,
    )
    stderr_text = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        print(stderr_text, file=sys.stderr)
        return completed.returncode

    try:
        stdout_text = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"便携运行时进度输出不是 UTF-8: {exc}", file=sys.stderr)
        return 3

    try:
        events = [json.loads(line) for line in stdout_text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        print(f"便携运行时进度输出不是有效的逐行 JSON: {exc}", file=sys.stderr)
        return 4

    if not events or any(event.get("type") != "progress" for event in events):
        print("便携运行时没有输出有效的进度事件", file=sys.stderr)
        return 5

    if not any("文件" in str(event.get("message", "")) for event in events):
        print("便携运行时的中文进度消息未正确恢复", file=sys.stderr)
        return 6

    print(f"便携运行时协议验证通过：{len(events)} 条 UTF-8 进度事件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

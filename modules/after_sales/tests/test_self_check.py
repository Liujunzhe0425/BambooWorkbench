import io
import json
import os
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))

from after_sales_agent import cli as module_cli  # noqa: E402


def test_cli_reconfigures_cp1252_streams_to_utf8(monkeypatch):
    raw_output = io.BytesIO()
    cp1252_stdout = io.TextIOWrapper(raw_output, encoding="cp1252", newline="\n")
    monkeypatch.setattr(module_cli.sys, "stdout", cp1252_stdout)

    module_cli._configure_standard_streams()
    print("售后自检通过", file=module_cli.sys.stdout)
    module_cli.sys.stdout.flush()

    assert raw_output.getvalue().decode("utf-8").strip() == "售后自检通过"


def test_progress_protocol_is_utf8_safe_on_gbk_stdout(monkeypatch):
    raw_output = io.BytesIO()
    gbk_stdout = io.TextIOWrapper(raw_output, encoding="gbk", newline="\n")
    monkeypatch.setattr(module_cli.sys, "stdout", gbk_stdout)

    module_cli._notify_progress(
        None,
        {"total": 2, "completed": 1, "message": "正在处理第 1/2 个文件"},
    )
    gbk_stdout.flush()

    protocol_bytes = raw_output.getvalue()
    assert protocol_bytes.isascii()
    event = json.loads(protocol_bytes.decode("utf-8"))
    assert event == {
        "type": "progress",
        "percent": 50,
        "message": "正在处理第 1/2 个文件",
    }


def test_self_check_runs():
    completed = subprocess.run(
        [str(MODULE_DIR / "run_module.bat"), "self-check"],
        cwd=MODULE_DIR,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr


def test_module_launcher_reports_version():
    if os.name != "nt":
        return
    env = os.environ.copy()
    env.update({"PYTHON_EXE": sys.executable})
    completed = subprocess.run(
        [str(MODULE_DIR / "run_module.bat"), "version"],
        cwd=MODULE_DIR,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "after_sales 1.3.4"


def test_frozen_module_root_resolves_to_portable_module(monkeypatch):
    executable = MODULE_DIR / "runtime" / "after_sales_agent.exe"
    monkeypatch.setattr(module_cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(module_cli.sys, "executable", str(executable))

    assert module_cli._module_root() == MODULE_DIR


def test_launcher_allows_explicit_python_override_before_bundled_runtime():
    launcher = (MODULE_DIR / "run_module.bat").read_text(encoding="utf-8")

    runtime_position = launcher.index("runtime\\after_sales_agent.exe")
    python_position = launcher.index("if defined PYTHON_EXE")
    assert python_position < runtime_position


def test_module_source_has_no_credential_or_direct_network_channel():
    source_root = MODULE_DIR / "src"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(source_root.rglob("*.py"))
    ).casefold()
    requirements = (MODULE_DIR / "requirements.txt").read_text(encoding="utf-8").casefold()

    assert "import keyring" not in source
    assert "urllib.request" not in source
    assert "import httpx" not in source
    assert "deepseek_gateway" not in source
    assert "module_ai_config" not in source
    assert "keyring" not in requirements

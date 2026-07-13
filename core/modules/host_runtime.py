import sys
from pathlib import Path


def module_host_command(arguments: list[str]) -> tuple[str, list[str]]:
    """Return a module-host command for source and frozen application modes."""
    if getattr(sys, "frozen", False):
        host = Path(sys.executable).resolve().with_name("BambooModuleHost.exe")
        if not host.is_file():
            raise FileNotFoundError("packaged module host is missing")
        return str(host), list(arguments)
    host_script = Path(__file__).with_name("process_host.py").resolve()
    return sys.executable, [str(host_script), *arguments]


def add_packaged_host_environment(environment: object) -> None:
    if not getattr(sys, "frozen", False):
        return
    host = Path(sys.executable).resolve().with_name("BambooModuleHost.exe")
    environment.insert("BAMBOO_MODULE_HOST", str(host))

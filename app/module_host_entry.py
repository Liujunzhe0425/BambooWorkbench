import sys
from collections.abc import Sequence

from core.modules.process_host import main as process_host_main
from mock_modules.common.cli import main as mock_module_main


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = list(sys.argv[1:] if arguments is None else arguments)
    if parsed and parsed[0] == "--mock-module":
        return mock_module_main(parsed[1:])
    return process_host_main(parsed)


if __name__ == "__main__":
    raise SystemExit(main())

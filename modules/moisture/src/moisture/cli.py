"""Command-line health surface for the moisture module."""

import argparse
import sys
from collections.abc import Sequence

from moisture import __version__
from moisture.infrastructure.diagnostics import collect_runtime_issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moisture")
    parser.add_argument("command", choices=("version", "self-check"))
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "version":
        sys.stdout.write(f"{__version__}\n")
        return 0

    issues = collect_runtime_issues()
    if issues:
        for issue in issues:
            sys.stderr.write(f"moisture self-check: {issue}\n")
        return 4

    sys.stderr.write("moisture self-check: ok\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

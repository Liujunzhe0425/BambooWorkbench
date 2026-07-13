import argparse
from pathlib import Path

from core.contracts.validator import validate_module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate"])
    parser.add_argument("module_dir", type=Path)
    args = parser.parse_args()
    report = validate_module(args.module_dir.resolve())
    for issue in report.issues:
        print(f"{issue.code}: {issue.message}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

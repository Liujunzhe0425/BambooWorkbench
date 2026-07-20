"""Offline CLI for governed experience administration."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from moisture.adapters.experience.local_editable_repository import (
    ExperienceAdminError,
    LocalEditableExperienceRepository,
)
from moisture.application.experience_management import ExperienceManagementService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage-experience")
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    show = commands.add_parser("show")
    validate = commands.add_parser("validate")
    create = commands.add_parser("create")
    for item in (validate, create):
        item.add_argument("--document", type=Path, required=True)
    for name in ("update", "publish", "retire"):
        item = commands.add_parser(name)
        item.add_argument("experience_id")
        item.add_argument("version")
        item.add_argument("--expected-hash", required=True)
        if name == "update":
            item.add_argument("--document", type=Path, required=True)
    show.add_argument("experience_id")
    show.add_argument("version")
    return parser


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main(arguments: list[str] | None = None) -> int:
    try:
        options = build_parser().parse_args(arguments)
        service = ExperienceManagementService(LocalEditableExperienceRepository(options.root))
        if options.command == "list":
            result = [asdict(item) for item in service.list()]
        elif options.command == "show":
            result = asdict(service.show(options.experience_id, options.version))
        elif options.command == "validate":
            result = asdict(service.validate(_read(options.document)))
        elif options.command == "create":
            result = asdict(service.create(_read(options.document)))
        elif options.command == "update":
            result = asdict(
                service.update(
                    options.experience_id,
                    options.version,
                    _read(options.document),
                    options.expected_hash,
                )
            )
        elif options.command == "publish":
            result = asdict(
                service.publish(options.experience_id, options.version, options.expected_hash)
            )
        else:
            result = asdict(
                service.retire(options.experience_id, options.version, options.expected_hash)
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ExperienceAdminError, OSError, UnicodeError, KeyError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

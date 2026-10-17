from __future__ import annotations

import argparse
from importlib import import_module
import sys

COMMANDS = ("aggregate", "plan", "receipt", "restore")


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="python3 -m ci.products")
    parser.add_argument("command", choices=tuple(sorted(COMMANDS)))
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser.parse_args(arguments)
        return 0
    command = parser.parse_args(arguments[:1]).command
    try:
        return import_module(f".{command}", __package__).main(arguments[1:])
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())

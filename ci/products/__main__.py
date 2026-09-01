from __future__ import annotations

import argparse
import sys

from . import aggregate, plan, receipt, restore


COMMANDS = {
    "aggregate": aggregate.main,
    "plan": plan.main,
    "receipt": receipt.main,
    "restore": restore.main,
}


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="python3 -m ci.products")
    parser.add_argument("command", choices=tuple(sorted(COMMANDS)))
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser.parse_args(arguments)
        return 0
    command = parser.parse_args(arguments[:1]).command
    try:
        return COMMANDS[command](arguments[1:])
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys

from . import receipt


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments.pop(0) != "receipt":
        raise SystemExit("usage: python3 -m ci.products receipt ...")
    return receipt.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())

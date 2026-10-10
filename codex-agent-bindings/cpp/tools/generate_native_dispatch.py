#!/usr/bin/env python3
"""Generate the C++ wrapper's native dispatch inventory and macro headers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def render(header: Path, include: Path) -> dict[str, str]:
    declarations = set(re.findall(r"\b(codex_agent_[A-Za-z0-9_]+)\s*\(", header.read_text()))
    sources = "\n".join(
        path.read_text()
        for path in sorted(include.glob("*.hpp"))
        if path.name not in {"native_dispatch.hpp", "native_remap.hpp", "native_unmap.hpp"}
    )
    symbols = sorted(
        symbol for symbol in declarations
        if re.search(rf"\b{re.escape(symbol)}\b", sources)
    )
    inventory = "".join(
        f"CODEX_AGENT_NATIVE_SYMBOL(s{index:03d}, {symbol})\n"
        for index, symbol in enumerate(symbols)
    )
    remap = "#pragma once\n\n#ifndef CODEX_AGENT_CPP_STATIC_TEST_DISPATCH\n" + "".join(
        f"#define {symbol} " + chr(92) + "\n" +
        f"    ::codex_agent::detail::NativeEntry<decltype(&::{symbol}), " + chr(92) + "\n" +
        f"        ::codex_agent::detail::NativeSymbol::s{index:03d}>::call\n"
        for index, symbol in enumerate(symbols)
    ) + "#endif\n"
    unmap = "#ifndef CODEX_AGENT_CPP_STATIC_TEST_DISPATCH\n" + "".join(
        f"#undef {symbol}\n" for symbol in symbols
    ) + "#endif\n"
    return {
        "native_symbols.inc": inventory,
        "native_remap.hpp": remap,
        "native_unmap.hpp": unmap,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--include", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = render(args.header, args.include)
    stale = []
    for name, content in outputs.items():
        destination = args.include / name
        if args.check:
            if not destination.is_file() or destination.read_text() != content:
                stale.append(str(destination))
        else:
            destination.write_text(content)
    if stale:
        raise SystemExit("stale generated native dispatch: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

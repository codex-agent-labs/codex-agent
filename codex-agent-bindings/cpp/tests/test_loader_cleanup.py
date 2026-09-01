#!/usr/bin/env python3
"""Prove loader child processes leave no private Runtime snapshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("library")
    parser.add_argument("compatibility")
    parser.add_argument("bad_library")
    arguments = parser.parse_args()
    root = Path(tempfile.gettempdir()).resolve()
    invalid = root / f"codex-agent-invalid-runtime-{id(arguments)}"
    invalid.write_bytes(b"not a runtime")
    commands = (
        [arguments.executable, arguments.library, arguments.compatibility, "success"],
        [arguments.executable, arguments.library, arguments.compatibility, "failure", arguments.bad_library],
        [arguments.executable, arguments.library, arguments.compatibility, "failure", str(invalid)],
        [arguments.executable, arguments.library, arguments.compatibility, "source-aba"],
    )
    try:
        for command in commands:
            child = subprocess.Popen(command)
            prefix = f"codex-agent-runtime-{child.pid}-"
            result = child.wait(timeout=30)
            if result != 0:
                raise SystemExit(f"loader child exited {result}: {command}")
            leaked = sorted(path for path in root.iterdir() if path.name.startswith(prefix))
            if leaked:
                raise SystemExit(f"loader child leaked snapshots: {leaked}")
    finally:
        invalid.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

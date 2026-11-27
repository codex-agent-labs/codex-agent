"""The production loader archive must not contain the synthetic trust-root hook."""

from __future__ import annotations

import subprocess
import sys


def main() -> None:
    result = subprocess.run([sys.argv[1], "-g", sys.argv[2]], check=True,
                            capture_output=True, text=True)
    if "set_native_loader_test_root" in result.stdout or "loader_test_root_public" in result.stdout:
        raise AssertionError("production loader contains a test trust-root hook")


if __name__ == "__main__":
    main()

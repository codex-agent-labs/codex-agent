"""Matching-host smoke test for an installed codex-agent wheel."""

import argparse
import asyncio
import tempfile
from pathlib import Path

from codex_agent import ClientInfo, CodexHost, HostState, HostStateKind


async def smoke(library: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-agent-python-consumer-") as root:
        bundle = Path(root, "empty-bundle")
        data = Path(root, "data")
        bundle.mkdir()
        data.mkdir()

        host = CodexHost(
            bundle,
            data,
            ClientInfo("installed-consumer", "Installed consumer", "1"),
            library_path=library,
        )
        try:
            initial = host.state.current
            if initial != HostState(HostStateKind.NEW):
                raise RuntimeError(f"expected a new Host, got {initial!r}")
        finally:
            await host.aclose()

        await host.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path, help="exact matching-host C-ABI library")
    library = parser.parse_args().library.resolve(strict=True)
    if not library.is_file():
        parser.error(f"library is not a file: {library}")
    asyncio.run(smoke(library))
    print(f"installed-wheel Host smoke passed with {library}")


if __name__ == "__main__":
    main()

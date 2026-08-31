"""Executable Host -> Agent -> Conversation installed-package consumer source."""

import argparse
import asyncio
from pathlib import Path

from codex_agent import ClientInfo, CodexHost, HostStateReady


async def run(host: CodexHost) -> None:
    await host.start()
    async with host.state.subscribe() as states:
        async for state in states:
            if isinstance(state, HostStateReady):
                conversation = await state.agent.conversations.open()
                async with conversation:
                    await conversation.send("Hello from Python")
                return
    raise RuntimeError("host closed before it became ready")


async def main(bundle: Path, data: Path, library: Path | None) -> None:
    async with CodexHost(
        bundle,
        data,
        ClientInfo("python-example", "Python example", "1.0.0"),
        library_path=library,
    ) as host:
        await run(host)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("data", type=Path)
    parser.add_argument("--library", type=Path)
    arguments = parser.parse_args()
    asyncio.run(main(arguments.bundle, arguments.data, arguments.library))

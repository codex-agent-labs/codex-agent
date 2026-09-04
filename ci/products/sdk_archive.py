"""Verify final SDK package archives that are not Maven carriers."""

from __future__ import annotations

import argparse
import io
from pathlib import Path, PurePosixPath
import stat
import tarfile

from .inventory import read_regular_file_bytes, sha256_bytes, write_canonical_json


NPM_COMPATIBILITY_PATH = "package/META-INF/codex-agent/sdk-compatibility.json"


def verify_npm_sdk_compatibility(archive: Path, compatibility_file: Path, output: Path) -> None:
    archive_bytes = read_regular_file_bytes(
        archive, max_bytes=1024 * 1024 * 1024, reject_symlink_parents=True,
    )
    compatibility = read_regular_file_bytes(
        compatibility_file, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    declarations: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as package:
        seen: set[str] = set()
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            normalized = str(path) + ("/" if member.isdir() else "")
            if (normalized in seen or normalized != member.name or
                    any(ord(character) < 32 or ord(character) == 127 for character in member.name) or
                    "\\" in member.name or path.is_absolute() or ".." in path.parts or
                    member.issym() or member.islnk() or not (member.isfile() or member.isdir())):
                raise ValueError(f"unsafe or duplicate npm archive member: {member.name}")
            seen.add(normalized)
            if member.isfile() and path.name == "sdk-compatibility.json":
                source = package.extractfile(member)
                if source is None:
                    raise ValueError("npm compatibility archive member has no payload")
                declarations.append((member.name, source.read()))
    if declarations != [(NPM_COMPATIBILITY_PATH, compatibility)]:
        raise ValueError("npm archive SDK compatibility inventory mismatch")
    write_canonical_json(output, {
        "schemaVersion": 1,
        "result": "passed",
        "archive": {"path": archive.name, "sha256": sha256_bytes(archive_bytes)},
        "sdkCompatibility": {
            "path": NPM_COMPATIBILITY_PATH,
            "sha256": sha256_bytes(compatibility),
        },
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--compatibility", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    verify_npm_sdk_compatibility(
        args.archive.resolve(), args.compatibility.resolve(), args.output.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import io
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest

from ci.products.inventory import load_canonical_json
from ci.products.sdk_archive import NPM_COMPATIBILITY_PATH, verify_npm_sdk_compatibility


def _tar(path: Path, members: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, contents in members:
            entry = tarfile.TarInfo(name)
            entry.mode = stat.S_IFREG | 0o644
            entry.size = len(contents)
            archive.addfile(entry, io.BytesIO(contents))


class SdkArchiveTest(unittest.TestCase):
    def test_npm_archive_binds_one_exact_compatibility_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(b'{"schemaVersion":1}\n')
            archive = root / "codex-agent.tgz"
            output = root / "evidence.json"
            _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), ("package/index.js", b"")])
            verify_npm_sdk_compatibility(archive, compatibility, output)
            evidence = load_canonical_json(output)
            self.assertEqual("passed", evidence["result"])
            self.assertEqual(NPM_COMPATIBILITY_PATH, evidence["sdkCompatibility"]["path"])

            for members in (
                [("package/wrong/sdk-compatibility.json", compatibility.read_bytes())],
                [(NPM_COMPATIBILITY_PATH, b"changed")],
                [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes())] * 2,
                [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), ("package/a//b", b"")],
                [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), ("package/bad\nname", b"")],
            ):
                with self.subTest(members=members):
                    _tar(archive, members)
                    with self.assertRaisesRegex(ValueError, "inventory mismatch|duplicate"):
                        verify_npm_sdk_compatibility(archive, compatibility, output)


if __name__ == "__main__":
    unittest.main()

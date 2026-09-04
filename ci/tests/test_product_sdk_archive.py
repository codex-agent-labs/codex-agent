from __future__ import annotations

import io
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest

from ci.products.inventory import canonical_json_bytes, load_canonical_json
from ci.products.sdk_archive import NPM_COMPATIBILITY_PATH, main, verify_npm_sdk_compatibility
from ci.tests.test_products import sdk_compatibility


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
            compatibility.write_bytes(canonical_json_bytes(sdk_compatibility()))
            archive = root / "codex-agent-0.2.0.tgz"
            output = root / "evidence.json"
            metadata = ("package/package.json", b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}')
            _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes()), metadata])
            verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            evidence = load_canonical_json(output)
            self.assertEqual("passed", evidence["result"])
            self.assertEqual(NPM_COMPATIBILITY_PATH, evidence["sdkCompatibility"]["path"])
            self.assertEqual(
                ["linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"],
                evidence["sdkCompatibility"]["embeddedTargets"],
            )

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
                        verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")

            compatibility.write_bytes(b'{"schemaVersion":1}\n')
            _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes())])
            with self.assertRaises(ValueError):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")

    def test_npm_identity_matches_requested_phase_and_compatibility_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = root / "sdk-compatibility.json"
            archive = root / "codex-agent-0.2.0.tgz"
            output = root / "evidence.json"
            declaration = sdk_compatibility()
            compatibility.write_bytes(canonical_json_bytes(declaration))
            metadata = ("package/package.json", b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}')

            def pack(record: tuple[str, bytes] | None = metadata) -> None:
                _tar(archive, [(NPM_COMPATIBILITY_PATH, compatibility.read_bytes())]
                     + ([record] if record else []))

            pack()
            self.assertEqual(0, main([
                "--archive", str(archive), "--compatibility", str(compatibility),
                "--output", str(output), "--version", "0.2.0",
            ]))
            self.assertEqual("0.2.0", load_canonical_json(output)["sdkVersion"])
            for contents in (
                b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.1"}',
                b'{"name":"other","version":"0.2.0"}',
                b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.1","version":"0.2.0"}',
                b'[]',
            ):
                with self.subTest(metadata=contents):
                    pack(("package/package.json", contents))
                    with self.assertRaises(ValueError):
                        verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            pack(None)
            with self.assertRaises(ValueError):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")
            pack()
            with self.assertRaisesRegex(ValueError, "archive SDK version"):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.1")
            declaration["sdkVersion"] = "0.2.1"
            compatibility.write_bytes(canonical_json_bytes(declaration))
            pack()
            with self.assertRaisesRegex(ValueError, "compatibility SDK version"):
                verify_npm_sdk_compatibility(archive, compatibility, output, sdk_version="0.2.0")


if __name__ == "__main__":
    unittest.main()

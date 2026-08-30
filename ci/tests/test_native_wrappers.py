from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

from native_wrappers import (  # noqa: E402
    HOSTS,
    LANGUAGES,
    deterministic_tar,
    deterministic_zip,
    host_classifier,
    safe_extract_tar,
    safe_extract_zip,
)


class NativeWrapperReleaseTest(unittest.TestCase):
    def test_release_inventory_is_exact(self) -> None:
        self.assertEqual(
            ["macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"],
            list(HOSTS),
        )
        self.assertEqual(("python", "csharp", "rust", "cpp", "dart"), LANGUAGES)
        self.assertEqual(
            {
                "macos-arm64": "lib/libcodex_agent.dylib",
                "macos-x64": "lib/libcodex_agent.dylib",
                "linux-arm64": "lib/libcodex_agent.so",
                "linux-x64": "lib/libcodex_agent.so",
                "windows-x64": "bin/codex_agent.dll",
            },
            {classifier: value[4] for classifier, value in HOSTS.items()},
        )

    def test_host_classifier_is_exact_and_fail_closed(self) -> None:
        for classifier, (system, architectures, *_rest) in HOSTS.items():
            with patch("platform.system", return_value=system), patch(
                "platform.machine", return_value=next(iter(architectures))
            ):
                self.assertEqual(classifier, host_classifier())
        with patch("platform.system", return_value="Linux"), patch(
            "platform.machine", return_value="riscv64"
        ):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                host_classifier()

    def test_release_archives_are_reproducible_and_safely_extractable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested/payload").write_bytes(b"payload")
            digests: list[tuple[str, str]] = []
            for index in range(2):
                zip_path = root / f"package-{index}.zip"
                tar_path = root / f"package-{index}.tar.gz"
                deterministic_zip(source, zip_path, "package")
                deterministic_tar(source, tar_path, "package")
                digests.append((
                    hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                    hashlib.sha256(tar_path.read_bytes()).hexdigest(),
                ))
                safe_extract_zip(zip_path, root / f"zip-{index}")
                safe_extract_tar(tar_path, root / f"tar-{index}")
                self.assertEqual(b"payload", (root / f"zip-{index}/package/nested/payload").read_bytes())
                self.assertEqual(b"payload", (root / f"tar-{index}/package/nested/payload").read_bytes())
            self.assertEqual(digests[0], digests[1])

    def test_extractors_reject_cross_platform_escape_and_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, name in enumerate(("../escape", "..\\escape", "C:\\escape")):
                archive = root / f"malicious-{index}.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(name, b"escape")
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    safe_extract_zip(archive, root / f"zip-output-{index}")
            duplicate_zip = root / "duplicate.zip"
            with zipfile.ZipFile(duplicate_zip, "w") as output:
                output.writestr("package/value", b"first")
                output.writestr("package/value", b"second")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                safe_extract_zip(duplicate_zip, root / "duplicate-zip-output")

            for index, name in enumerate(("../escape", "..\\escape", "C:\\escape")):
                archive = root / f"malicious-{index}.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    member = tarfile.TarInfo(name)
                    member.size = 6
                    output.addfile(member, io.BytesIO(b"escape"))
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    safe_extract_tar(archive, root / f"tar-output-{index}")
            duplicate_tar = root / "duplicate.tar.gz"
            with tarfile.open(duplicate_tar, "w:gz") as output:
                for payload in (b"first", b"second"):
                    member = tarfile.TarInfo("package/value")
                    member.size = len(payload)
                    output.addfile(member, io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                safe_extract_tar(duplicate_tar, root / "duplicate-tar-output")


if __name__ == "__main__":
    unittest.main()

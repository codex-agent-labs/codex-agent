import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

from ci.products.inventory import sha256_file
from ci.products.toolchain_capture_bootstrap import prepare


class CaptureBootstrapTest(unittest.TestCase):
    def test_pinned_inputs_precede_dependency_only_compiler_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = root / "plugin.jar"
            plugin.write_bytes(b"pinned Kotlin plugin")
            archive = root / "native.tar.gz"
            prefix = "kotlin-native-prebuilt-linux-x86_64-2.3.10"
            with tarfile.open(archive, "w:gz") as target:
                for relative, data in (
                    ("bin/konanc", b"#!/bin/sh\n"),
                    ("konan/compiler.fingerprint", b"1234567890abcdef"),
                    ("konan/konan.properties", b"dependenciesUrl=https://download.jetbrains.com/kotlin/native\n"),
                    ("konan/lib/kotlin-native-compiler-embeddable.jar", b"compiler"),
                ):
                    entry = tarfile.TarInfo(f"{prefix}/{relative}")
                    entry.size = len(data)
                    entry.mode = 0o755 if relative == "bin/konanc" else 0o644
                    target.addfile(entry, io.BytesIO(data))
            plugin_name = "kotlin-gradle-plugin-2.3.10-gradle813.jar"
            archive_name = "kotlin-native-prebuilt-2.3.10-linux-x86_64.tar.gz"
            metadata = (
                "<verification-metadata><components><component>"
                f'<artifact name="{plugin_name}"><sha256 value="{sha256_file(plugin)[7:]}"/></artifact>'
                f'<artifact name="{archive_name}"><sha256 value="{sha256_file(archive)[7:]}"/></artifact>'
                "</component></components></verification-metadata>"
            ).encode()
            authorities = {
                "gradle/libs.versions.toml": b'[versions]\nkotlin = "2.3.10"\n',
                "runtime/gradle/verification-metadata.xml": metadata,
            }
            output = root / "out"
            konan = root / "konan"
            with mock.patch.dict(os.environ, {"RUNNER_OS": "Linux", "RUNNER_ARCH": "X64"}), \
                    mock.patch("ci.products.toolchain_capture_bootstrap.git_regular_blob_bytes",
                               side_effect=lambda _, __, path: authorities[path]), \
                    mock.patch("ci.products.toolchain_capture_bootstrap.subprocess.run") as run:
                paths = prepare(root, "a" * 40, "linux-x64", output, konan,
                                plugin_source=plugin, archive_source=archive)
                self.assertEqual(archive_name, Path(paths["archive"]).name)
                self.assertEqual(plugin_name, Path(paths["plugin"]).name)
                self.assertTrue(Path(paths["compiler"]).joinpath("bin/konanc").is_file())
                command = run.call_args.args[0]
                self.assertEqual((str(Path(paths["compiler"]) / "bin/konanc"),
                                  "-target", "linux_x64", "-Xcheck-dependencies"), command)
                self.assertEqual(str(konan), run.call_args.kwargs["env"]["KONAN_DATA_DIR"])
                self.assertTrue(run.call_args.kwargs["check"])

                tampered = root / "tampered.tar.gz"
                tampered.write_bytes(archive.read_bytes() + b"x")
                with self.assertRaisesRegex(ValueError, "Git-pinned SHA-256"):
                    prepare(root, "a" * 40, "linux-x64", root / "rejected", root / "rejected-konan",
                            plugin_source=plugin, archive_source=tampered)
                self.assertFalse((root / "rejected-konan" / prefix).exists())


if __name__ == "__main__":
    unittest.main()

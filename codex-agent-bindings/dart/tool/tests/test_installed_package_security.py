"""Offline path-installed Dart package trust check; not a release receipt."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from ci.native_wrappers import deterministic_tar, safe_extract_tar, stage_dart_release


ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "codex-agent-bindings/dart"
PUBLIC_ROOT = ROOT / "gradle/release/keys/sdk-runtime-root.pub"
LIBRARIES = (
    "macos-arm64/libcodex_agent.dylib",
    "macos-x64/libcodex_agent.dylib",
    "linux-arm64/libcodex_agent.so",
    "linux-x64/libcodex_agent.so",
    "windows-x64/codex_agent.dll",
)


@unittest.skipUnless(shutil.which("dart"), "Dart is not installed")
class InstalledDartPackageSecurityTest(unittest.TestCase):
    def test_offline_path_install_rejects_unattested_override_and_missing_root(self):
        with tempfile.TemporaryDirectory(prefix="codex-agent-dart-installed-") as base:
            work = Path(base).resolve()
            staged = work / "staged"
            stage_dart_release(SOURCE, staged)
            native = staged / "lib/src/native"
            root = native / "sdk-runtime-root.pub"
            root.write_bytes(PUBLIC_ROOT.read_bytes())
            for member in LIBRARIES:
                library = native / member
                library.parent.mkdir(parents=True, exist_ok=True)
                library.write_bytes(b"tampered Runtime fixture")
            compatibility = json.loads((native / "sdk-compatibility.json").read_bytes())
            version = compatibility["sdkVersion"]
            archive = work / f"codex-agent-dart-{version}.tar.gz"
            deterministic_tar(staged, archive, f"codex_agent-{version}")
            extracted = work / "archive"
            safe_extract_tar(archive, extracted)
            package = extracted / f"codex_agent-{version}"
            native = package / "lib/src/native"
            root = native / "sdk-runtime-root.pub"
            pubspec = (package / "pubspec.yaml").read_text()
            self.assertEqual(["codex_agent"], re.findall(r"(?m)^name: (\S+)$", pubspec))
            self.assertEqual([compatibility["sdkVersion"]], re.findall(r"(?m)^version: (\S+)$", pubspec))
            consumer = work / "consumer"
            (consumer / "bin").mkdir(parents=True)
            (consumer / "pubspec.yaml").write_text(
                "name: installed_security_probe\n"
                "publish_to: none\n"
                "environment:\n  sdk: '>=3.6.0 <4.0.0'\n"
                f"dependencies:\n  codex_agent:\n    path: {os.path.relpath(package, consumer)}\n"
            )
            (consumer / "bin/probe.dart").write_text(
                "import 'dart:io';\n"
                "import 'package:codex_agent/src/ffi.dart';\n"
                "void main(List<String> args) {\n"
                "  try { if (args.single == '--default') { NativeApi.loadResolved(); }\n"
                "    else { NativeApi.load(args.single); }\n"
                "    stderr.writeln('unexpected native load'); exitCode = 2;\n"
                "  } catch (error) { stdout.writeln(error); }\n"
                "}\n"
            )
            library = work / "untrusted-library.dylib"
            library.write_bytes(b"not a native library")
            cache = work / "pub-cache"
            (cache / "hosted").mkdir(parents=True)
            source_cache = Path(os.environ.get("PUB_CACHE", Path.home() / ".pub-cache"))
            (cache / "hosted/pub.dev").symlink_to(source_cache / "hosted/pub.dev", target_is_directory=True)
            environment = dict(os.environ)
            environment["PUB_CACHE"] = str(cache)
            environment.pop("CODEX_AGENT_LIBRARY", None)
            installed = subprocess.run(
                ["dart", "pub", "get", "--offline"], cwd=consumer,
                env=environment, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
            configured = json.loads((consumer / ".dart_tool/package_config.json").read_text())
            binding = next(item["rootUri"] for item in configured["packages"]
                           if item["name"] == "codex_agent")
            self.assertEqual(package, (consumer / ".dart_tool" / binding).resolve())

            def probe(path: str) -> str:
                result = subprocess.run(
                    ["dart", "run", "bin/probe.dart", path],
                    cwd=consumer, env=environment, capture_output=True,
                    text=True, timeout=45,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertNotIn("unexpected native load", result.stderr)
                return result.stdout

            self.assertIn("embedded Codex Agent Runtime digest mismatch", probe("--default"))
            for member in LIBRARIES:
                (native / member).unlink()
            self.assertIn("is absent; pass libraryPath", probe("--default"))
            self.assertIn("release-keyring.json is absent", probe(str(library)))
            root.unlink()
            self.assertIn("SDK root is absent", probe(str(library)))
            root.write_bytes(b"not an Ed25519 key\n")
            self.assertIn("public key is not canonical", probe(str(library)))
            root.write_bytes(b"x" * 4097)
            self.assertIn("has invalid size", probe(str(library)))


if __name__ == "__main__":
    unittest.main()

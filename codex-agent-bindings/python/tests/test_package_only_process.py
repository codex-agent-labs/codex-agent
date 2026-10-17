"""Synthetic Python package-only process proof, not genuine Runtime admission."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1]
REPOSITORY = SOURCE.parents[1]
sys.path.insert(0, str(REPOSITORY))

from ci.native_wrappers import PYTHON_TAGS, package_python  # noqa: E402


class PythonPackageOnlyProcessTest(unittest.TestCase):
    def test_synthetic_sdist_and_five_wheels_need_no_compiler_or_linker(self) -> None:
        try:
            expected = {"build": "1.3.0", "setuptools": "80.9.0", "wheel": "0.45.1"}
            if any(importlib.metadata.version(name) != version
                   for name, version in expected.items()):
                self.skipTest("the reviewed Python package-tool versions are unavailable")
        except importlib.metadata.PackageNotFoundError:
            self.skipTest("local Python package build dependencies are unavailable")

        with tempfile.TemporaryDirectory(prefix="python-package-only-") as temporary:
            root = Path(temporary)
            source = root / "source"
            shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(
                "tests", "consumer", "parity", "__pycache__", "*.pyc"))
            native = source / "src/codex_agent/native"
            native.mkdir()
            (native / "sdk-compatibility.json").write_bytes(b"{}\n")
            (native / "sdk-runtime-root.pub").write_bytes(b"synthetic root\n")
            libraries = {
                "macos-arm64": "libcodex_agent.dylib",
                "macos-x64": "libcodex_agent.dylib",
                "linux-arm64": "libcodex_agent.so",
                "linux-x64": "libcodex_agent.so",
                "windows-x64": "codex_agent.dll",
            }
            for classifier, name in libraries.items():
                target = native / classifier
                target.mkdir()
                (target / name).write_bytes(b"synthetic prebuilt runtime\n")
            output, work = root / "packages", root / "work"
            output.mkdir()
            work.mkdir()
            forbidden = str(root / "compiler-or-linker-must-not-run")
            with mock.patch.dict(os.environ, {
                "CC": forbidden, "CXX": forbidden, "CPP": forbidden,
                "LDSHARED": forbidden, "AR": forbidden, "RANLIB": forbidden,
            }):
                package_python(source, output, work)
            self.assertEqual(6, len(list(output.iterdir())))
            for classifier, tag in PYTHON_TAGS.items():
                wheel = output / f"codex_agent-0.8.0-py3-none-{tag}.whl"
                self.assertTrue(wheel.is_file())
                with zipfile.ZipFile(wheel) as archive:
                    member = f"codex_agent/native/{classifier}/{libraries[classifier]}"
                    self.assertEqual(b"synthetic prebuilt runtime\n", archive.read(member))


if __name__ == "__main__":
    unittest.main()

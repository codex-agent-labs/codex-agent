"""Compiler-free check of Cargo's package-verification marker and native members."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIBRARIES = (
    "native/osx-arm64/libcodex_agent.dylib",
    "native/osx-x64/libcodex_agent.dylib",
    "native/linux-arm64/libcodex_agent.so",
    "native/linux-x64/libcodex_agent.so",
    "native/win-x64/codex_agent.dll",
)


class PackageAssetsTest(unittest.TestCase):
    def test_package_verification_rejects_missing_or_empty_runtime_assets(self) -> None:
        cargo = os.environ.get("CODEX_AGENT_TEST_CARGO") or shutil.which("cargo")
        rustc = Path(cargo).with_name("rustc") if cargo else None
        if rustc is None or not rustc.is_file():
            self.skipTest("local Rust compiler is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "build-script"
            subprocess.run([str(rustc), str(ROOT / "build.rs"), "-o", str(script)], check=True)
            (root / "Cargo.toml.orig").touch()
            output = root / "out"
            output.mkdir()
            environment = os.environ | {
                "CARGO_MANIFEST_DIR": str(root),
                "OUT_DIR": str(output),
                "CARGO_CFG_TARGET_OS": "macos",
                "CARGO_CFG_TARGET_ARCH": "aarch64",
            }

            def run_script() -> subprocess.CompletedProcess[str]:
                return subprocess.run([str(script)], cwd=root, env=environment, capture_output=True, text=True)

            self.assertNotEqual(run_script().returncode, 0)
            for name in ("native/sdk-compatibility.json", *LIBRARIES):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            self.assertEqual(run_script().returncode, 0)
            (root / LIBRARIES[0]).write_bytes(b"")
            self.assertNotEqual(run_script().returncode, 0)

    def test_cargo_lists_the_verification_marker_and_all_staged_runtime_libraries(self) -> None:
        cargo = os.environ.get("CODEX_AGENT_TEST_CARGO") or shutil.which("cargo")
        if cargo is None:
            self.skipTest("local Cargo is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "rust"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns("target", "__pycache__"))
            for name in LIBRARIES:
                path = source / name
                path.parent.mkdir(parents=True)
                path.write_bytes(b"fixture")
            result = subprocess.run(
                [cargo, "package", "--list", "--locked", "--offline", "--allow-dirty"],
                cwd=source, capture_output=True, text=True, check=True,
            )
            members = set(result.stdout.splitlines())
            self.assertIn("Cargo.toml.orig", members)
            self.assertIn("native/sdk-compatibility.json", members)
            self.assertTrue(set(LIBRARIES) <= members)


if __name__ == "__main__":
    unittest.main()

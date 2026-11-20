"""Test-only consumer overlay; no package or native-host acceptance claims."""

import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.products.inventory import regular_file_inventory, snapshot_regular_tree
from ci.products.sdk_package import run_rust_fixture_consumer


class RustFixtureConsumerTest(unittest.TestCase):
    def test_exact_private_overlay_executes_one_test_and_preserves_installed_sources(self):
        repository = Path(__file__).resolve().parents[2]
        original = repository / "codex-agent-bindings/rust"
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary).resolve() / "package"
            snapshot_regular_tree(original / "src", package / "src")
            for name in ("Cargo.toml", "Cargo.lock", "build.rs", "native/sdk-compatibility.json"):
                path = package / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((original / name).read_bytes())
            (package / "native/sdk-runtime-root.pub").write_bytes(
                (repository / "gradle/release/keys/sdk-runtime-root.pub").read_bytes())
            program = original / "consumer/src/bin/lifecycle_smoke.rs"
            fixture = package.parent / "unit-only-mock.dylib"
            fixture.write_bytes(b"mocked process seam; not a native binary")
            before = regular_file_inventory(package)
            stdout, stderr = io.BytesIO(), io.BytesIO()
            environment = {**os.environ, "CARGO_TARGET_DIR": str(package.parent / "existing-consumer-target")}

            def execute(command, **options):
                root = options["cwd"]
                self.assertEqual(["cargo", "test", "--manifest-path", str(root / "Cargo.toml"),
                    "--lib", "--release", "--locked", "--offline", "codex_installed_fixture::main", "--", "--exact"], command)
                self.assertEqual(str(fixture), options["env"]["CODEX_AGENT_INSTALLED_TEST_FIXTURE"])
                self.assertEqual(environment["CARGO_TARGET_DIR"], options["env"]["CARGO_TARGET_DIR"])
                self.assertEqual({"sdk-runtime-root.pub", "sdk-compatibility.json"},
                                 {path.name for path in (root / "native").iterdir()})
                self.assertEqual((package / "src/lib.rs").read_bytes() +
                    b"\n#[cfg(test)]\nmod codex_installed_fixture;\n", (root / "src/lib.rs").read_bytes())
                unit = (root / "src/codex_installed_fixture.rs").read_text()
                self.assertIn("CodexNativeLibrary::load_fixture_for_test(&library)?", unit)
                self.assertIn("block_on(conversation.send(\"Hello from Rust\")?)?", unit)
                self.assertIn("CodexNativeLibrary::take_cleanup_issues().is_empty()", unit)
                return subprocess.CompletedProcess(command, 0, self.test_stdout, b"unit compiler log")

            with patch("ci.products.sdk_package.subprocess.run", side_effect=execute), \
                    patch("sys.stdout", SimpleNamespace(buffer=stdout)), patch("sys.stderr", SimpleNamespace(buffer=stderr)):
                self.test_stdout = b"test codex_installed_fixture::main ... ok\ntest result: ok. 1 passed; 0 failed;\n"
                run_rust_fixture_consumer(package, program, fixture, environ=environment)
                self.assertEqual(before, regular_file_inventory(package))
                self.test_stdout = b"test result: ok. 0 passed; 0 failed;\n"
                with self.assertRaisesRegex(ValueError, "did not execute"):
                    run_rust_fixture_consumer(package, program, fixture, environ=environment)
                self.assertEqual(before, regular_file_inventory(package))


if __name__ == "__main__":
    unittest.main()

"""Raw producer composition checks, not compiler/host or signature acceptance."""

from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import regular_file_inventory
from ci.products.sdk_package import produce_authorized_rust_capabilities, rust_lifecycle_unit_source


class RustCapabilitiesTest(unittest.TestCase):
    def test_projection_preserves_real_loader_and_every_assertion(self):
        source = Path(__file__).resolve().parents[2] / "codex-agent-bindings/rust/tests/lifecycle.rs"
        original = source.read_bytes()
        unit = rust_lifecycle_unit_source(original)
        self.assertEqual(original.replace(b"use codex_agent::{", b"use crate::{"),
                         unit.replace(b"load_fixture_for_test(", b"load("))
        self.assertIn(b'CodexNativeLibrary::load(&path).expect("load real matching-host C SDK")', unit)
        self.assertEqual(15, unit.count(b"load_fixture_for_test("))
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            rust_lifecycle_unit_source(original.replace(b"CodexNativeLibrary::load(&path)", b"changed(&path)"))

    def test_composed_producer_retains_unit_and_parity_executables_and_cleans_sidecars(self):
        repository = Path(__file__).resolve().parents[2]
        original = repository / "codex-agent-bindings/rust"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sdks = root / "sdks"
            sdk = sdks / "macos-arm64"
            library = sdk / "lib/libcodex_agent.dylib"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"mocked subprocess input; not a genuine library")
            (sdk / "include").mkdir()
            (sdk / "include/codex_agent.h").write_text("fixture header")
            compatibility = sdks / "sdk-compatibility.json"
            compatibility.write_bytes((original / "native/sdk-compatibility.json").read_bytes())
            (sdks / "sdk-runtime-root.pub").write_bytes(
                (repository / "gradle/release/keys/sdk-runtime-root.pub").read_bytes())
            authorization = root / "external-sidecars"
            authorization.mkdir()
            (authorization / "fixture").write_bytes(b"mocked authentication context, no signature claim")
            canonical, bootstrap = root / "canonical.json", root / "bootstrap.json"
            canonical.write_bytes(b"input fixture")
            bootstrap.write_bytes(b"input fixture")
            before = regular_file_inventory(sdks)
            output = root / "output"
            sidecar = library.with_name(library.name + ".evidence")
            missing = False
            executed = []

            def execute(command, **options):
                executed.append(command)
                if "--doc" in command:
                    self.assertEqual(["cargo", "test", "--doc", "--locked", "--offline",
                        "--message-format=json", "--", "--include-ignored", "--test-threads=1"], command)
                    self.assertEqual(str(options["cwd"] / "target"), options["env"]["CARGO_TARGET_DIR"])
                    options["stdout"].write(b"mocked doctest execution; not compiler acceptance\n")
                    return subprocess.CompletedProcess(command, 0)
                self.assertEqual(["cargo", "test", "--lib", "--test", "enum_parity", "--locked", "--offline",
                                  "--message-format=json", "--", "--include-ignored", "--test-threads=1"], command)
                self.assertEqual(str(library), options["env"]["CODEX_AGENT_REAL_SDK"])
                self.assertEqual(regular_file_inventory(authorization), regular_file_inventory(sidecar))
                source = options["cwd"]
                self.assertEqual((original / "tests/lifecycle.rs").read_bytes(), (source / "tests/lifecycle.rs").read_bytes())
                self.assertEqual(rust_lifecycle_unit_source((original / "tests/lifecycle.rs").read_bytes()),
                                 (source / "tests/lifecycle_unit.rs").read_bytes())
                self.assertIn(b'#[cfg(test)]\n#[path = "../tests/lifecycle_unit.rs"]', (source / "src/lib.rs").read_bytes())
                self.assertEqual({"sdk-compatibility.json", "sdk-runtime-root.pub"},
                                 {path.name for path in (source / "native").iterdir()})
                raw = source / "target/cross-language-evidence"
                raw.mkdir(parents=True)
                (raw / "compiler-evidence.tsv").write_text("compilerEvidenceId\tpublicSymbols\nfixture\tSymbol\n")
                (raw / "executed-tests.tsv").write_text("executedTestId\tstatus\n" +
                    "".join(f"fixture-{index:03d}\tpassed\n" for index in range(556)))
                for suffix in (".c", ".tsv", "", ".exe"):
                    (raw / ("real-sdk-leaf-service-null-boundary" + suffix)).write_bytes(b"mocked raw evidence")
                for index, name in enumerate(("src/lib.rs", "tests/enum_parity.rs")):
                    if missing and index == 1:
                        continue
                    executable = source / f"target/debug/deps/test-{index}"
                    executable.parent.mkdir(parents=True, exist_ok=True)
                    executable.write_bytes(name.encode())
                    options["stdout"].write(json.dumps({"reason": "compiler-artifact",
                        "manifest_path": str(source / "Cargo.toml"), "profile": {"test": True},
                        "target": {"src_path": str(source / name)}, "executable": str(executable)}).encode() + b"\n")
                options["stdout"].write(b'{"reason":"build-finished","success":true}\n')
                return subprocess.CompletedProcess(command, 0)

            def produce():
                with patch("ci.products.sdk_package.verified_native_consumer_authorization",
                           return_value=nullcontext(authorization)) as authenticated, \
                        patch("ci.products.sdk_package.subprocess.run", side_effect=execute):
                    produce_authorized_rust_capabilities(repository, canonical_api=canonical,
                        c_abi_bootstrap=bootstrap, c_sdk_root=sdk, native_library=library,
                        sdk_compatibility=compatibility, output=output,
                        runtime_authorization=authorization, expected_classifier="macos-arm64")
                    authenticated.assert_called_once_with(authorization, sdks, "macos-arm64")

            produce()
            self.assertEqual(2, len(executed))
            self.assertEqual(2, len(regular_file_inventory(output / "cargo-test-executables")))
            self.assertEqual((original / "tests/enum_parity.rs").read_bytes(), (output / "test-program").read_bytes())
            self.assertEqual(before, regular_file_inventory(sdks))
            self.assertFalse(sidecar.exists())
            self.assertTrue((output / "source/tests/lifecycle_unit.rs").is_file())
            missing = True
            with self.assertRaisesRegex(ValueError, "inventory is incomplete"):
                produce()
            self.assertFalse(output.exists())
            self.assertFalse(sidecar.exists())
            self.assertEqual(before, regular_file_inventory(sdks))


if __name__ == "__main__":
    unittest.main()

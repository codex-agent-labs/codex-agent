"""Raw producer composition checks, not compiler/host or signature acceptance."""

from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import regular_file_inventory
from ci.products.sdk_package import produce_authorized_native_capabilities, rust_lifecycle_unit_source


class RustCapabilitiesTest(unittest.TestCase):
    def test_python_reuses_authenticated_sidecars_and_cleans_failed_suite(self):
        self._check_authenticated_sidecars_and_failed_suite("python")

    def test_dart_reuses_authenticated_sidecars_and_cleans_failed_suite(self):
        self._check_authenticated_sidecars_and_failed_suite("dart")

    def test_csharp_projection_keeps_loader_tests_and_cleans_failed_restore(self):
        self._check_authenticated_sidecars_and_failed_suite("csharp")

    def _check_authenticated_sidecars_and_failed_suite(self, language):
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sdks = root / "sdks"
            sdk = sdks / "macos-arm64"
            library = sdk / "lib/libcodex_agent.dylib"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"mocked subprocess input; not a genuine library")
            (sdk / "include").mkdir()
            (sdk / "include/codex_agent.h").write_bytes(b"fixture header")
            compatibility = sdks / "sdk-compatibility.json"
            compatibility.write_bytes(b"fixture declaration; no authentication claim")
            root_public = (repository / "gradle/release/keys/sdk-runtime-root.pub").read_bytes()
            (sdks / "sdk-runtime-root.pub").write_bytes(root_public)
            authorization = root / "authorization"
            authorization.mkdir()
            (authorization / "fixture").write_bytes(b"mocked authenticated context")
            canonical, bootstrap = root / "canonical.json", root / "bootstrap.json"
            canonical.write_bytes(b"fixture")
            bootstrap.write_bytes(b"fixture")
            output = root / "output"
            extra = {}
            if language == "dart":
                dart_runner = root / "test/bin/test.dart"
                dart_runner.parent.mkdir(parents=True)
                dart_runner.write_bytes(b"mocked test runner")
                config = root / "package_config.json"
                config.write_text(json.dumps({"configVersion": 2, "packages": [
                    {"name": "test", "rootUri": (root / "test").as_uri() + "/", "packageUri": "lib/"},
                    {"name": "codex_agent", "rootUri": (repository / "codex-agent-bindings/dart").as_uri() + "/", "packageUri": "lib/"},
                ]}))
                extra = {"dart_executable": "declared-dart", "package_config": config}
            elif language == "csharp":
                compatibility.write_bytes((repository / "codex-agent-bindings/rust/native/sdk-compatibility.json").read_bytes())
                dotnet = root / "dotnet"
                dotnet.write_bytes(b"mocked executable, no compiler evidence")
                extra = {"dotnet": dotnet}
            before = regular_file_inventory(sdks)
            sidecar = library.with_name(library.name + ".evidence")

            def execute(command, **options):
                source = options["cwd"]
                if language == "python":
                    self.assertEqual([sys.executable, "-m", "unittest", "discover", "-s",
                                      str(source / "tests"), "-v"], command)
                    self.assertEqual(str(library), options["env"]["CODEX_AGENT_LIBRARY"])
                    self.assertEqual(str(repository), options["env"]["PYTHONPATH"].split(os.pathsep)[0])
                    resource = "src/codex_agent/native/sdk-runtime-root.pub"
                elif language == "dart":
                    self.assertEqual(["declared-dart", f"--packages={source / '.dart_tool/package_config.json'}",
                                      str(dart_runner), "--reporter", "expanded", "test"], command)
                    self.assertEqual(str(library), options["env"]["CODEX_AGENT_REAL_LIBRARY"])
                    self.assertEqual(str(library), options["env"]["CODEX_AGENT_LIBRARY"])
                    generated = (source / "lib/src/ffi.dart").read_text()
                    self.assertIn("final fixture = _capabilityFixtures[path];", generated)
                    self.assertIn("RuntimeCompatibility.load().verifyRuntimeIdentity(", generated)
                    self.assertIn("runtimeFileSha256(File(path)) != fixture.digest", generated)
                    for name in ("leaf_service", "conversation", "agent", "host"):
                        projected = (source / f"test/{name}_parity.dart").read_text()
                        original = (repository / f"codex-agent-bindings/dart/test/{name}_parity.dart").read_text()
                        self.assertEqual(original, projected.split("\n", 1)[1].replace(
                            "return registerCapabilityFixture(output);", "return output;"))
                    resource = "lib/src/native/sdk-runtime-root.pub"
                else:
                    self.assertEqual([str(dotnet), "restore"], command[:2])
                    self.assertIn("--no-cache", command)
                    projected = (source / "tests/CodexAgent.Tests/McpValueParity.cs").read_text()
                    original = (repository / "codex-agent-bindings/csharp/tests/CodexAgent.Tests/McpValueParity.cs").read_text()
                    self.assertEqual(original, projected.replace("NativeLibraryLoader.LoadCapabilityProjection(sdkPath);",
                                                                "CodexNativeLibrary.Configure(sdkPath);"))
                    loader = (source / "src/CodexAgent/Interop/NativeLibraryLoader.CapabilityProjection.cs").read_text()
                    self.assertEqual(2, loader.count("Digest(File.ReadAllBytes(path)) != expected"))
                    self.assertIn("ValidateLoadedLibrary(handle, compatibility, RuntimeTarget, true);", loader)
                    self.assertEqual((repository / "codex-agent-bindings/csharp/tests/CodexAgent.Tests/RuntimeLoaderSecurity.cs").read_bytes(),
                                     (source / "tests/CodexAgent.Tests/RuntimeLoaderSecurity.cs").read_bytes())
                if language != "csharp":
                    self.assertEqual(root_public, (source / resource).read_bytes())
                self.assertEqual(regular_file_inventory(authorization), regular_file_inventory(sidecar))
                raise subprocess.CalledProcessError(1, command)

            with patch("ci.products.sdk_package.verified_native_consumer_authorization",
                       return_value=nullcontext(authorization)) as authenticated, \
                    patch("ci.products.sdk_package.subprocess.run", side_effect=execute) as runner:
                with self.assertRaises(subprocess.CalledProcessError):
                    produce_authorized_native_capabilities(repository, language=language, canonical_api=canonical,
                        c_abi_bootstrap=bootstrap, c_sdk_root=sdk, native_library=library,
                        sdk_compatibility=compatibility, output=output,
                        runtime_authorization=authorization, expected_classifier="macos-arm64", **extra)
                authenticated.assert_called_once_with(authorization, sdks, "macos-arm64")
                runner.assert_called_once()
            if language == "csharp":
                self.assertEqual({"dotnet-restore-execution.json"}, {p.name for p in output.iterdir()})
            else:
                self.assertFalse(output.exists())
            self.assertFalse(sidecar.exists())
            self.assertEqual(before, regular_file_inventory(sdks))

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
                    produce_authorized_native_capabilities(repository, language="rust", canonical_api=canonical,
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

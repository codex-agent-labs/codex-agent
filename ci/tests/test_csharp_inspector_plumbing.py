"""Explicit inspector plumbing; source/projection/tool capability seams are fixtures."""

from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_wrappers as wrappers
import tooling_inspector
from products import sdk_native, sdk_package
from products.inventory import canonical_json_bytes, load_canonical_json_bytes
from products.receipt import write_output_manifest
from products.registry import NATIVE_TARGETS
from ci.tests.product_chain_support import write_receipt


class CsharpInspectorPlumbingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inspector-plumbing-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        repository = Path(__file__).resolve().parents[2]
        self.compatibility = (repository / "codex-agent-bindings/csharp/native/sdk-compatibility.json").read_bytes()
        self.root_key = (repository / sdk_native.SDK_ROOT_PATH).read_bytes()
        self.version = load_canonical_json_bytes(self.compatibility)["sdkVersion"]
        self.sdks = self.root / "sdks"
        self.sdks.mkdir()
        (self.sdks / "sdk-compatibility.json").write_bytes(self.compatibility)
        (self.sdks / "sdk-runtime-root.pub").write_bytes(self.root_key)
        self.stage = self.root / "stage"
        self.packages = self.stage / "outputs"
        archive = self.packages / "csharp" / f"CodexAgent.{self.version}.nupkg"
        archive.parent.mkdir(parents=True)
        with ZipFile(archive, "w") as output:
            for name, raw in {"lib/net8.0/CodexAgent.dll": b"fixture assembly",
                "META-INF/codex-agent/sdk-compatibility.json": self.compatibility,
                "META-INF/codex-agent/sdk-runtime-root.pub": self.root_key}.items():
                info = ZipInfo(name)
                info.external_attr = 0o100644 << 16
                output.writestr(info, raw)
        evidence = self.packages / "evidence"
        evidence.mkdir()
        (evidence / "sdk-compatibility.json").write_bytes(self.compatibility)
        (evidence / "sdk-runtime-root.pub").write_bytes(self.root_key)
        manifest = write_output_manifest(self.stage, "sdk", "csharp", "package", "desktop", self.version,
            {"package": "outputs/csharp", "evidence": "outputs/evidence"})
        self.receipt_path = self.root / "package-receipt.json"
        self.receipt = write_receipt(self.receipt_path, product="sdk", component="csharp", phase="package",
            target="desktop", version=self.version, version_identity=self.version,
            outputs=manifest["outputs"], upstream=[], context={"producer": {
                "repository": "fixture/repository", "workflowPath": None, "commit": "a" * 40,
                "tree": "b" * 40, "event": "local", "runId": None, "runAttempt": None, "pullRequest": None}})
        self.capability = SimpleNamespace(verify_resources=Mock(side_effect=self.verify_resources))
        self.require = self.enterContext(patch.object(tooling_inspector, "require_inspector",
            side_effect=self.require_inspector, create=True))

    def require_inspector(self, value):
        # Exact private-type/liveness enforcement itself belongs to the real helper tests.
        if value is not self.capability:
            raise ValueError("fixture inspector is not the current authenticated capability")
        return value

    def verify_resources(self, assembly, root, compatibility):
        self.assertEqual(b"fixture assembly", assembly.read_bytes())
        self.assertEqual(self.root_key, root.read_bytes())
        self.assertEqual(self.compatibility, compatibility.read_bytes())

    def test_same_capability_reaches_both_real_package_passes(self):
        sources, binary = self.root / "sources", self.root / "binary"
        (sources / "csharp/native").mkdir(parents=True)
        (sources / "csharp/native/sdk-compatibility.json").write_bytes(self.compatibility)
        (sources / "csharp/native/sdk-runtime-root.pub").write_bytes(self.root_key)
        binary.mkdir()
        for name in wrappers.CSHARP_BINARY_FILES - {"sdk-compatibility.json", "sdk-runtime-root.pub"}:
            (binary / name).write_bytes(b"fixture imported binary")
        observed = []
        def process(*command, **kwargs):
            if command[1] == "pack":
                target = Path(command[command.index("--output") + 1])
                (target / f"CodexAgent.{self.version}.nupkg").write_bytes(b"fixture package")
        def gate(output, sdks, version, language, *, csharp_inspector):
            self.assertEqual((self.sdks, self.version, "csharp"), (sdks, version, language))
            self.assertIs(self.capability, csharp_inspector)
            observed.append((output / "csharp" / f"CodexAgent.{version}.nupkg").read_bytes())
        with patch.object(wrappers, "verify_sdk_dotnet_toolchain"), \
             patch.object(wrappers, "require_prepared_native_assets"), \
             patch.object(wrappers, "set_source_sdk_version"), \
             patch.object(wrappers, "require_csharp_binary"), \
             patch.object(wrappers, "run", side_effect=process), \
             patch.object(wrappers, "normalize_nupkg"), \
             patch.object(wrappers, "write_package_toolchains"), \
             patch.object(wrappers, "verify_native_wrapper_sdk_packages", side_effect=gate):
            wrappers.package_all(sources, self.sdks, self.root / "result", self.version,
                ("csharp",), binary, self.root / "fixture-profile", csharp_inspector=self.capability)
        self.assertEqual([b"fixture package", b"fixture package"], observed)

    def test_full_wrapper_gate_uses_capability_and_propagates_failure_without_fallback(self):
        with patch.object(wrappers, "run", side_effect=AssertionError("No inspector build")) as build, \
             patch.object(wrappers.subprocess, "run", side_effect=AssertionError("No fallback process")) as process, \
             patch.object(wrappers, "require_embedded_package_versions") as versions, \
             patch.object(wrappers, "require_embedded_native_assets") as assets:
            wrappers.verify_native_wrapper_sdk_packages(self.packages, self.sdks, self.version,
                "csharp", csharp_inspector=self.capability)
            self.capability.verify_resources.assert_called_once()
            versions.assert_called_once_with(self.packages, self.version, ("csharp",))
            assets.assert_called_once_with(self.packages, self.sdks, self.version, ("csharp",))
            self.capability.verify_resources.side_effect = ValueError("fixture inspector rejected CLR resources")
            with self.assertRaisesRegex(ValueError, "rejected CLR"):
                wrappers.verify_native_wrapper_sdk_packages(self.packages, self.sdks, self.version,
                    "csharp", csharp_inspector=self.capability)
            self.assertEqual(1, versions.call_count)
            self.assertEqual(1, assets.call_count)
            build.assert_not_called()
            process.assert_not_called()

    def test_none_keeps_legacy_build_and_execution_without_capability_import(self):
        self.require.side_effect = AssertionError("Default path must not use the new helper")
        with patch.object(wrappers, "run") as build, patch.object(wrappers.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="")) as execute:
            wrappers.require_embedded_sdk_compatibility(self.packages, self.sdks, self.version, ("csharp",))
        self.assertEqual(["restore", "build"], [call.args[1] for call in build.call_args_list])
        self.assertEqual("dotnet", execute.call_args.args[0][0])
        self.assertTrue(execute.call_args.args[0][1].endswith("bin/Debug/net8.0/VerifySdkRuntimeRoot.dll"))
        self.require.assert_not_called()

    def test_non_csharp_and_wrong_or_expired_capability_reject_before_work(self):
        for selection in (("python",), wrappers.LANGUAGES):
            for method in (wrappers.package_all, wrappers.package_once):
                with self.assertRaisesRegex(ValueError, "exact C#"):
                    method(Path("missing"), Path("missing"), Path("missing"), self.version, selection,
                           csharp_inspector=self.capability)
            with self.assertRaisesRegex(ValueError, "exact C#"):
                wrappers.require_embedded_sdk_compatibility(Path("missing"), Path("missing"),
                    self.version, selection, csharp_inspector=self.capability)
        with self.assertRaisesRegex(ValueError, "exact C#"):
            wrappers.verify_native_wrapper_sdk_packages(Path("missing"), Path("missing"), self.version,
                "python", csharp_inspector=self.capability)
        for method, args in (
            (wrappers.package_all, (Path("missing"), Path("missing"), Path("missing"), self.version, ("csharp",))),
            (wrappers.package_once, (Path("missing"), Path("missing"), Path("missing"), self.version, ("csharp",))),
            (wrappers.require_embedded_sdk_compatibility, (Path("missing"), Path("missing"), self.version, ("csharp",))),
            (wrappers.verify_native_wrapper_sdk_packages, (Path("missing"), Path("missing"), self.version, "csharp"))):
            with self.subTest(method=method.__name__), self.assertRaisesRegex(ValueError, "authenticated capability"):
                method(*args, csharp_inspector=object())
        self.require.side_effect = ValueError("expired fixture inspector")
        with self.assertRaisesRegex(ValueError, "expired"):
            wrappers.require_embedded_sdk_compatibility(self.packages, self.sdks, self.version,
                ("csharp",), csharp_inspector=self.capability)
        self.capability.verify_resources.assert_not_called()

    def test_native_receipt_gate_forwards_the_exact_capability(self):
        with patch.object(sdk_native, "verify_staged_native_sdk_inputs", return_value={"sdkVersion": self.version}), \
             patch.object(wrappers, "verify_native_wrapper_sdk_packages") as gate:
            receipt, raw = sdk_native.verify_native_sdk_package_phase(self.stage, self.receipt_path,
                self.root / "request", self.root / "runtime", self.sdks, self.root_key,
                csharp_inspector=self.capability)
        self.assertEqual(self.receipt, receipt)
        self.assertEqual(self.receipt_path.read_bytes(), raw)
        self.assertEqual({"csharp_inspector": self.capability}, gate.call_args.kwargs)
        with patch.object(sdk_native, "validate_phase_receipt", return_value={**self.receipt, "component": "python"}), \
             self.assertRaisesRegex(ValueError, "exact C#"):
            sdk_native.verify_native_sdk_package_phase(self.stage, self.receipt_path, self.root / "request",
                self.root / "runtime", self.sdks, self.root_key, csharp_inspector=self.capability)

    def test_full_package_entry_rejects_non_csharp_before_staging(self):
        with patch.object(sdk_package, "_receipt", return_value=({**self.receipt, "component": "python"}, b"fixture")), \
             patch.object(sdk_package, "stage_sdk_inputs", side_effect=AssertionError("No input staging")), \
             self.assertRaisesRegex(ValueError, "exact C#"):
            sdk_package.verify_sdk_package_inputs(self.root, self.stage, self.receipt_path,
                self.root / "request", csharp_inspector=self.capability)

    def test_full_package_entry_preserves_capability_at_native_gate(self):
        # Stop at the real delegation: cryptographic projections and original plan replay
        # are explicit seams here, not fabricated authenticated production evidence.
        binary = self.root / "binary"
        binary.mkdir()
        (binary / "fixture").write_bytes(b"fixture binary")
        common = self.root / "common"
        common.write_bytes(b"fixture original")
        aggregate = self.root / "aggregate.json"
        aggregate.write_bytes(canonical_json_bytes({"runtimeVersion": "0.2.0", "runtimeCompatibilityVersion": "0.2.0"}))
        args = {name: common for name in ("contract_payload", "contract_attestation", "contract_attestation_signature",
            "contract_public_key", "contract_metadata_receipt", "runtime_metadata_receipt")}
        args.update(runtime_manifest=aggregate, required_trust_domain="fixture", contract_keyring=None,
                    contract_keys_directory=None, runtime_keyring=None, runtime_keys_directory=None)
        args["variant_phase_receipts"] = {target: {"package": common, "validation": common} for target in NATIVE_TARGETS}
        for name in ("variant_bundles", "variant_attestations", "variant_attestation_signatures", "variant_public_keys"):
            args[name] = {target: common for target in NATIVE_TARGETS}
        def receipt(path):
            if path == self.receipt_path: return self.receipt, self.receipt_path.read_bytes()
            if path == self.root / "binary-receipt": return {**self.receipt, "phase": "binary"}, b"fixture"
            return {"product": "contract", "component": "contract", "phase": "metadata", "target": "common"}, b"fixture"
        def stage(_request, handoff):
            handoff.mkdir()
            (handoff / sdk_package.COMPATIBILITY_NAME).write_bytes(canonical_json_bytes(
                {"sdkVersion": self.version, "contract": {"version": "0.2.0"}}))
        class GateReached(Exception): pass
        with ExitStack() as stack:
            for name, kwargs in {
                "_receipt": {"side_effect": receipt}, "stage_sdk_inputs": {"side_effect": stage},
                "load_sdk_compatibility_request": {"return_value": args},
                "verify_contract_component_projection": {"return_value": object()},
                "_native_runtime_projections_from_request": {"return_value": object()},
                "git_regular_blob_bytes": {"return_value": self.root_key},
                "phase_instance_dependencies": {"return_value": []}, "_verify_plan": {},
            }.items(): stack.enter_context(patch.object(sdk_package, name, **kwargs))
            stack.enter_context(patch("products.sdk_csharp_binary.verify_csharp_binary_stage"))
            gate = stack.enter_context(patch.object(sdk_native, "verify_native_sdk_package_phase", side_effect=GateReached))
            with self.assertRaises(GateReached):
                sdk_package.verify_sdk_package_inputs(self.root, self.stage, self.receipt_path, self.root / "request",
                    runtime_stage_root=self.root / "runtime", staged_sdks=self.sdks, binary_stage_root=binary,
                    binary_receipt_path=self.root / "binary-receipt", csharp_inspector=self.capability)
            self.assertEqual({"csharp_inspector": self.capability}, gate.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()

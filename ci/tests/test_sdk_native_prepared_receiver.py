"""Five-SDK receiver composition; mocked authorities are not hosted proof."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_native_prepared_receiver as receiver
from products.inventory import canonical_json_bytes, regular_file_inventory
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId


class NativePreparedReceiverTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-native-receiver-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "build").mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"original plan\n")
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        for path in (self.discovery, self.state):
            path.mkdir()
            (path / "original").write_bytes(b"original\n")
        self.destination = self.root / "build/received"
        self.keyring = self.root / "keyring.json"
        self.keyring.write_bytes(b"keyring\n")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 11, "runAttempt": 1, "pullRequest": 31}
        self.anchor = {"schemaVersion": 1, "product": "sdk", "component": "python",
            "phase": "package", "target": "desktop", "buildKey": "sha256:" + "c" * 64,
            "inputs": {}}
        self.instances = {}
        for target in NATIVE_TARGETS:
            for phase in ("package", "validation"):
                instance = PhaseInstanceId("runtime", target, phase, target)
                stage = self.root / f"original-{target}-{phase}"
                stage.mkdir()
                (stage / "original").write_bytes(str(instance).encode())
                receipt_path = stage / "receipt.json"
                raw = f"receipt-{target}-{phase}\n".encode()
                receipt_path.write_bytes(raw)
                receipt = {"product": "runtime", "component": target, "phase": phase,
                    "target": target, "productVersion": "0.8.0", "outputs": []}
                self.instances[instance] = {"stage": stage, "receiptPath": receipt_path,
                    "receipt": receipt, "raw": raw}
        sdk = self.root / "sdk-inputs"
        sdk.mkdir()
        (sdk / receiver.REQUEST_NAME).write_bytes(b"request\n")
        self.inputs = {"selection": {"sdkVersion": "0.8.0",
            "contractPayloadSha256": "sha256:" + "d" * 64,
            "consumers": [{"product": "sdk", "component": "python",
                           "phase": "package", "target": "desktop"}]},
            "sdk": {"directory": sdk},
            "runtime": {"originalPhases": self.instances,
                        "receiptBytes": {key: value["raw"] for key, value in self.instances.items()}}}
        self.events = []
        self.content_failure = False
        self.exit_failure = False
        self.predecessor_failure = False

    @contextmanager
    def verified(self, *args, **kwargs):
        self.events.append("enter")
        self.assertEqual((self.plan, self.discovery, self.state), args)
        yield self.inputs
        self.events.append("exit")
        if self.exit_failure:
            raise ValueError("original context changed at exit")

    def captured(self, plan, path, **kwargs):
        self.events.append("capture")
        self.assertEqual(self.anchor, kwargs["expected_phase_plan"])
        source = path / "original/prepared-sources"
        for language in NATIVE_BINDINGS:
            (source / language).mkdir(parents=True)
            (source / language / "source").write_bytes(language.encode())
        sdk = path / "original/staged-sdks"
        sdk.mkdir(parents=True)
        (sdk / "sdk").write_bytes(b"staged")
        return {"captureProducer": self.producer}

    def materialized(self, *args, **kwargs):
        self.events.append("materialize")
        path = args[4]
        path.mkdir()
        (path / "producer.json").write_bytes(canonical_json_bytes(self.producer))
        receipt = path / "contract-contract-metadata-common/phase-receipt.json"
        receipt.parent.mkdir()
        receipt.write_bytes(canonical_json_bytes({"product": "contract", "component": "contract",
            "phase": "metadata", "target": "common", "outputs": [
                {"kind": "contract-bundle", "sha256": "sha256:" + "d" * 64}]}))
        for target in NATIVE_TARGETS:
            for phase in ("package", "validation"):
                original = self.instances[PhaseInstanceId("runtime", target, phase, target)]
                elected = path / f"runtime-{target}-{phase}-{target}"
                shutil.copytree(original["stage"], elected / "stage")
                (elected / "phase-receipt.json").write_bytes(original["raw"])
        if self.predecessor_failure:
            (path / "runtime-macos-arm64-package-macos-arm64/phase-receipt.json").write_bytes(b"wrong")
        return self.anchor

    def capability(self, arguments, runtime, sdks, output):
        self.events.append("capability")
        (output / "contract").mkdir(parents=True)
        (output / "bootstrap").mkdir()
        (output / "contract/canonical-api.json").write_bytes(b"canonical\n")
        (output / "contract/canonical-coverage.json").write_bytes(b"coverage\n")
        (output / "bootstrap/bootstrap-evidence.json").write_bytes(b"bootstrap\n")

    def verify_content(self, *args):
        self.events.append("content")
        if self.content_failure:
            raise ValueError("tampered SDK")
        return {"sdkVersion": "0.8.0", "producerCommit": self.producer["commit"],
                "producerTree": self.producer["tree"]}

    def invoke(self, **changes):
        options = {"plan": self.plan, "discovery": self.discovery, "state": self.state,
            "preparation_state": self.state, "destination": self.destination,
            "preparation_component": "python", "preparation_phase": "package",
            "preparation_target": "desktop", "preparation_build_key": self.anchor["buildKey"],
            "prepared_artifact_id": 17, "prepared_artifact_sha256": "sha256:" + "e" * 64,
            "sdk_inputs_artifact_id": 18, "sdk_inputs_artifact_sha256": "sha256:" + "f" * 64,
            "trusted_workflow_sha": "a" * 40, "keyring": self.keyring,
            "keys_directory": self.keys, "repository_root": self.root,
            "environ": {}, "token": "token"}
        options.update(changes)
        with patch.object(receiver.sdk_workflow, "verified_inputs", side_effect=self.verified), \
             patch.object(receiver.product_reuse, "inspect_products", return_value={"readyPlans": [self.anchor]}), \
             patch.object(receiver, "validate_anchor", return_value=PhaseInstanceId("sdk", "python", "package", "desktop")), \
             patch.object(receiver.product_reuse, "capture_sdk_native_prepared_upload", side_effect=self.captured), \
             patch.object(receiver.product_reuse, "materialize_product_predecessors", side_effect=self.materialized), \
             patch.object(receiver.product_reuse, "validate_phase_receipt", side_effect=lambda value: value), \
             patch.object(receiver, "verify_output_manifest_identity", side_effect=lambda *a: {"outputs": []}), \
             patch.object(receiver, "git_regular_blob_bytes", return_value=b"root key"), \
             patch.object(receiver, "verify_staged_native_sdk_inputs", side_effect=self.verify_content) as verify_content, \
             patch.object(receiver, "_verify_prepared_sources") as verify_sources, \
             patch.object(receiver, "load_sdk_compatibility_request", return_value={}), \
             patch.object(receiver, "_stage_native_capability_inputs", side_effect=self.capability):
            return receiver.receive(**options), verify_content, verify_sources

    def test_all_five_sdk_content_is_checked_before_export(self):
        result, verifier, verify_sources = self.invoke()
        self.assertEqual(1, verifier.call_count)
        self.assertEqual(1, verify_sources.call_count)
        self.assertEqual("0.8.0", result["sdkVersion"])
        self.assertEqual(["enter", "capture", "materialize", "content", "capability", "exit"], self.events)
        upload = self.destination / "upload"
        self.assertEqual(b"canonical\n", (upload / "build/ci/sdk-contract-evidence/canonical-api.json").read_bytes())
        self.assertEqual(b"coverage\n", (upload / "build/ci/sdk-contract-evidence/canonical-coverage.json").read_bytes())
        self.assertEqual(b"bootstrap\n", (upload / "build/ci/sdk-runtime-evidence/bootstrap-evidence.json").read_bytes())
        self.assertTrue((upload / f"codex-agent-sdk/build/native-wrapper-c-abi-sdks/{self.producer['tree']}/sdk").is_file())
        self.assertEqual(set(NATIVE_BINDINGS), {path.name for path in
            (upload / "codex-agent-sdk/build/native-wrapper-package-sources").iterdir()})
        self.assertTrue(regular_file_inventory(self.destination / "prepared-upload"))

    def test_unselected_anchor_and_content_failure_never_export(self):
        self.inputs["selection"]["consumers"] = []
        with self.assertRaisesRegex(ValueError, "not selected"):
            self.invoke()
        self.assertFalse(self.destination.exists())
        self.inputs["selection"]["consumers"] = [{"product": "sdk", "component": "python",
            "phase": "package", "target": "desktop"}]
        self.content_failure = True
        with self.assertRaisesRegex(ValueError, "tampered SDK"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_late_original_context_failure_never_exports(self):
        self.exit_failure = True
        with self.assertRaisesRegex(ValueError, "original context changed at exit"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_elected_runtime_predecessor_mismatch_never_exports(self):
        self.predecessor_failure = True
        with self.assertRaisesRegex(ValueError, "predecessor differs from SDK original"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_prepared_source_bytes_must_match_verified_sdk_assets(self):
        sdks, source = self.root / "verified-sdks", self.root / "prepared-sources"
        native = sdks / "macos-arm64"
        for path, data in ((native / "lib/libcodex_agent.dylib", b"library"),
                           (native / "include/codex_agent.h", b"header"),
                           (native / receiver.C_ABI_PACKAGE_MANIFEST, b"manifest"),
                           (native / "codex-agent-c-abi-evidence.json", b"evidence"),
                           (sdks / "sdk-compatibility.json", b"compatibility"),
                           (sdks / "sdk-runtime-root.pub", b"root key")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        destinations = {
            "python/src/codex_agent/native/macos-arm64/libcodex_agent.dylib": native / "lib/libcodex_agent.dylib",
            "csharp/native/osx-arm64/libcodex_agent.dylib": native / "lib/libcodex_agent.dylib",
            "rust/native/osx-arm64/libcodex_agent.dylib": native / "lib/libcodex_agent.dylib",
            "dart/lib/src/native/macos-arm64/libcodex_agent.dylib": native / "lib/libcodex_agent.dylib",
            "cpp/native/macos-arm64/lib/libcodex_agent.dylib": native / "lib/libcodex_agent.dylib",
            "cpp/native/macos-arm64/include/codex_agent.h": native / "include/codex_agent.h",
        }
        for language, directory in (("python", "src/codex_agent/native"), ("csharp", "native"),
                                    ("rust", "native"), ("dart", "lib/src/native")):
            for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
                destinations[f"{language}/{directory}/{name}"] = sdks / name
        for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
            destinations[f"cpp/native/macos-arm64/share/CodexAgent/native/{name}"] = sdks / name
        for relative, original in destinations.items():
            output = source / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(original.read_bytes())
        index = {"targets": [{"classifier": "macos-arm64", "libraryPath": "lib/libcodex_agent.dylib"}]}
        with patch.object(receiver, "tree_entries", return_value=[]), \
             patch.object(receiver, "git_file_inventory", return_value=[]):
            receiver._verify_prepared_sources(source, sdks, index, self.root, "a" * 40)
            (source / "rust/native/osx-arm64/libcodex_agent.dylib").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "differ from producer Git"):
                receiver._verify_prepared_sources(source, sdks, index, self.root, "a" * 40)


if __name__ == "__main__":
    unittest.main()

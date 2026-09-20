"""Original iOS package context orchestration with all authority seams mocked.

Real phase shards, receipts, manifests, restoration, and execution descriptors
exercise byte pairing. Mocked upload, Git selection, signed SDK context, and final
package gate are not claims of CI, signature, host, or semantic acceptance.
"""

from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci import sdk_ios_original_package as workflow
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file,
    snapshot_regular_tree, write_canonical_json,
)
from ci.products.receipt import write_output_manifest
from ci.products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from ci.products.sdk_apple_package_execution import (
    _EVENTS, build_apple_package_execution_context,
)
from ci.products.sdk_inputs import REQUEST_NAME
from ci.tests.product_chain_support import write_receipt


class SdkIosOriginalPackageTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-original-package-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"historical plan authority seam"}\n')
        self.producer = {
            "repository": "owner/repository",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "event": "pull_request",
            "runId": 71,
            "runAttempt": 2,
            "pullRequest": 31,
        }
        self.upload = self.root / "upload-template"
        original = self.upload / "original"
        original.mkdir(parents=True)
        package_stage = self.root / "package-stage"
        (package_stage / "outputs/evidence").mkdir(parents=True)
        (package_stage / "outputs/apple").mkdir()
        self.compatibility_bytes = b"authenticated SDK compatibility\n"
        (package_stage / "outputs/evidence/sdk-compatibility.json").write_bytes(self.compatibility_bytes)
        (package_stage / "outputs/apple/CodexAgentPackage-0.8.0.zip").write_bytes(b"original package\x00\xff")
        manifest = write_output_manifest(
            package_stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
            {"evidence": "outputs/evidence", "apple": "outputs/apple"},
        )
        selected = write_receipt(
            self.root / "selected-package-receipt.json",
            product="sdk", component="sdk-ios", phase="package", target="ios", version="0.8.0",
            version_identity="0.8.0", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer},
        )
        self.receipt_path = self.root / "package-receipt.json"
        phase = {name: selected[name] for name in PHASE_PLAN_KEYS}
        finalized = finalize_phase_object(
            stage_root=package_stage, phase_plan=phase, producer=self.producer,
            product_version="0.8.0", trust_domain="development", destination=original / "shard",
        )
        self.receipt_bytes = finalized["receiptBytes"]
        self.receipt = finalized["receipt"]
        self.receipt_path.write_bytes(self.receipt_bytes)
        retained_plan = original / "original-plan/impact-plan.json"
        retained_plan.parent.mkdir(parents=True)
        retained_plan.write_bytes(self.plan.read_bytes())

        inputs = original / "inputs"
        inputs.mkdir()
        write_canonical_json(inputs / "producer.json", self.producer)
        write_canonical_json(inputs / "phase-plan.json", phase)
        self.predecessors = {}
        for product, component, predecessor_phase, target, version in (
            ("sdk", "sdk-ios", "binary", "ios", "0.8.0"),
            ("contract", "contract", "binary", "common", "0.2.0"),
            ("contract", "contract", "metadata", "common", "0.2.0"),
        ):
            directory = inputs / "-".join((product, component, predecessor_phase, target))
            stage = directory / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/artifact.bin").write_bytes(
                f"{product}/{component}/{predecessor_phase}/{target}\n".encode()
            )
            kind = "contract-bundle" if predecessor_phase == "metadata" else "fixture"
            predecessor_manifest = write_output_manifest(
                stage, product, component, predecessor_phase, target, version, {kind: "outputs"},
            )
            receipt_path = directory / "phase-receipt.json"
            value = write_receipt(
                receipt_path, product=product, component=component, phase=predecessor_phase,
                target=target, version=version, version_identity=version,
                outputs=predecessor_manifest["outputs"], upstream=[], context={"producer": self.producer},
            )
            self.predecessors[(product, predecessor_phase)] = (stage, receipt_path, value)

        execution = original / "package-execution"
        (execution / "events").mkdir(parents=True)
        for event in _EVENTS:
            directory = execution / "events" / event
            directory.mkdir()
            (directory / "combined.bin").write_bytes(b"")
        (execution / "input-binding.json").write_bytes(b"authenticated input binding\n")
        descriptor = build_apple_package_execution_context(
            capture_directory=execution,
            package_receipt=original / "shard/phase-receipt.json",
            binary_receipt=self.predecessors[("sdk", "binary")][1],
            contract_binary_receipt=self.predecessors[("contract", "binary")][1],
            contract_metadata_receipt=self.predecessors[("contract", "metadata")][1],
            producer=self.producer,
            sdk_compatibility=package_stage / "outputs/evidence/sdk-compatibility.json",
            sdk_inputs_artifact_id=811,
            sdk_inputs_artifact_sha256="sha256:" + "8" * 64,
        )
        write_canonical_json(original / "apple-package-execution.json", descriptor)

        self.keyring = self.root / "keyring.json"
        self.keyring.write_bytes(b"authenticated keyring\n")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        (self.tooling / "receipt.json").write_bytes(b"authenticated tooling seam\n")
        self.tooling_key = self.root / "tooling.pub"
        self.tooling_key.write_bytes(b"public key\n")
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"java, never launched\n")
        self.events = []
        self.upload_mutation = None
        self.consumer_producer = self.producer
        self.metadata_mismatch = False
        self.binary_mismatch = False
        self.context_exit_mutation = None
        self.gate_failure = False
        self.private_paths = []

    def capture_package(self, plan, destination, **arguments):
        self.events.append("package-capture")
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.receipt_path, arguments["package_receipt_path"])
        self.assertEqual((701, "sha256:" + "7" * 64),
                         (arguments["artifact_id"], arguments["artifact_sha256"]))
        snapshot_regular_tree(self.upload, destination, allow_empty=True)
        self.last_original = destination / "original"
        if self.upload_mutation == "phase-plan":
            value = json.loads((destination / "original/inputs/phase-plan.json").read_bytes())
            value["buildKey"] = "sha256:" + "d" * 64
            write_canonical_json(destination / "original/inputs/phase-plan.json", value)
        elif self.upload_mutation == "descriptor":
            value = json.loads((destination / "original/apple-package-execution.json").read_bytes())
            value["kind"] = "wrong-kind"
            write_canonical_json(destination / "original/apple-package-execution.json", value)
        self.private_paths.append(destination)
        return {"captureProducer": self.producer}

    def capture_sdk(self, plan, destination, **arguments):
        self.events.append("sdk-capture")
        self.assertEqual("current-runtime", arguments["expected_source"])
        self.assertEqual((811, "sha256:" + "8" * 64),
                         (arguments["artifact_id"], arguments["artifact_sha256"]))
        sdk = destination / "sdk"
        sdk.mkdir(parents=True)
        (sdk / REQUEST_NAME).write_bytes(b"authenticated compatibility request\n")
        authority = destination / "authority"
        authority.mkdir()
        metadata = authority / "metadata.json"
        metadata.write_bytes(self.predecessors[("contract", "metadata")][1].read_bytes())
        if self.metadata_mismatch:
            metadata.write_bytes(metadata.read_bytes() + b"changed\n")
        for name in ("attestation.json", "attestation.sig", "public-key.pub", "keyring.json"):
            (authority / name).write_bytes(f"authenticated {name}\n".encode())
        keys = authority / "keys"
        keys.mkdir()
        (keys / "release.pub").write_bytes(b"release key\n")
        signed = authority / "execution-closure/receipts"
        signed.mkdir(parents=True)
        (signed / "binary.json").write_bytes(self.predecessors[("contract", "binary")][1].read_bytes())
        if self.binary_mismatch:
            (signed / "binary.json").write_bytes((signed / "binary.json").read_bytes() + b"changed\n")
        self.sdk_paths = {"directory": sdk, "authority": authority, "metadata": metadata, "keys": keys}
        (destination / "transport.bin").write_bytes(b"authenticated SDK transport\n")
        self.private_paths.append(destination)
        return {"captureProducer": self.producer}

    @contextmanager
    def signed_inputs(self, capture, **arguments):
        self.events.append("signed-enter")
        self.assertEqual("current-runtime", arguments["expected_source"])
        expected_payload = self.predecessors[("contract", "metadata")][2]["outputs"][0]["sha256"]
        self.assertEqual(expected_payload, arguments["expected_contract_payload_sha256"])
        authority = self.sdk_paths["authority"]
        joined = {
            "sdk": {
                "directory": self.sdk_paths["directory"],
                "arguments": {
                    "contract_metadata_receipt": self.sdk_paths["metadata"],
                    "contract_attestation": authority / "attestation.json",
                    "contract_attestation_signature": authority / "attestation.sig",
                    "contract_public_key": authority / "public-key.pub",
                    "required_trust_domain": "release",
                    "contract_keyring": authority / "keyring.json",
                    "contract_keys_directory": self.sdk_paths["keys"],
                },
            },
            "runtime": {"synthetic": "authenticated runtime input"},
            "selection": {"synthetic": "authenticated SDK selection"},
        }
        try:
            yield joined
            self.events.append("signed-exit")
            if self.context_exit_mutation == "capture":
                (self.last_original / "apple-package-execution.json").write_bytes(b"changed on context exit\n")
            elif self.context_exit_mutation == "sdk-capture":
                (self.sdk_paths["directory"].parent / "transport.bin").write_bytes(b"changed on context exit\n")
            elif self.context_exit_mutation == "policy":
                self.keyring.write_bytes(b"changed policy on context exit\n")
        finally:
            self.events.append("signed-closed")

    def gate(self, repository, stage, receipt_path, request, **arguments):
        self.events.append("full-gate")
        if self.gate_failure:
            raise ValueError("synthetic full original package rejection")
        self.assertEqual(self.root, repository)
        self.assertEqual(self.receipt_bytes, receipt_path.read_bytes())
        self.assertEqual(self.sdk_paths["directory"] / REQUEST_NAME, request)
        self.assertEqual({"binary_stage_root", "binary_receipt_path", "binary_contract_evidence",
                          "apple_original_verification"}, set(arguments))
        self.assertEqual(self.last_original / "inputs/sdk-sdk-ios-binary-ios/stage",
                         arguments["binary_stage_root"])
        self.assertEqual(self.predecessors[("sdk", "binary")][1].read_bytes(),
                         arguments["binary_receipt_path"].read_bytes())
        evidence = arguments["binary_contract_evidence"]
        self.assertEqual({
            "stageRoot": str(self.last_original / "inputs/contract-contract-metadata-common/stage"),
            "phaseReceipt": str(self.last_original / "inputs/contract-contract-metadata-common/phase-receipt.json"),
            "attestation": str(self.sdk_paths["authority"] / "attestation.json"),
            "attestationSignature": str(self.sdk_paths["authority"] / "attestation.sig"),
            "publicKey": str(self.sdk_paths["authority"] / "public-key.pub"),
            "expectedTrustDomain": "release",
            "keyring": str(self.sdk_paths["authority"] / "keyring.json"),
            "keysDirectory": str(self.sdk_paths["keys"]),
        }, evidence)
        policy = arguments["apple_original_verification"]
        self.assertEqual({
            "repository": self.root,
            "tooling_evidence": self.tooling,
            "tooling_public_key": self.tooling_key,
            "java_executable": self.java,
            "policy_revision": "9" * 40,
            "required_trust_domain": "release",
            "tooling_keyring": None,
            "tooling_keys_directory": None,
        }, {name: policy[name] for name in (
            "repository", "tooling_evidence", "tooling_public_key", "java_executable",
            "policy_revision", "required_trust_domain", "tooling_keyring", "tooling_keys_directory",
        )})
        self.assertEqual(self.last_original / "package-execution/events", policy["evidence_directory"])
        self.assertEqual(self.last_original / "package-execution/input-binding.json",
                         policy["execution_binding_file"])
        self.assertEqual(
            sha256_bytes((self.last_original / "package-execution/input-binding.json").read_bytes()),
            policy["expected_binding_sha256"],
        )
        expected = json.loads(policy["expected_execution_files"].read_bytes())
        records = regular_file_inventory(self.last_original / "package-execution", allow_empty=True)
        self.assertEqual({
            record["relativePath"].removeprefix("events/"): record["sha256"].removeprefix("sha256:")
            for record in records if record["relativePath"].startswith("events/")
        }, expected)
        return self.receipt, self.receipt_bytes

    def validate_plan(self, path, repository, **arguments):
        self.assertEqual(self.last_original / "original-plan/impact-plan.json", path)
        self.assertEqual(self.root, repository)
        self.assertEqual({"expected_revision": self.producer["commit"]}, arguments)
        return {"synthetic": "validated historical plan", "remoteBuildAuthorized": True, "event": "pull_request"}

    def original_context(self, **changes):
        arguments = dict(
            artifact_id=701,
            artifact_sha256="sha256:" + "7" * 64,
            trusted_workflow_sha="c" * 40,
            keyring=self.keyring,
            keys_directory=self.keys,
            repository_root=self.root,
            environ={"GITHUB_RUN_ID": "current-untrusted-run"},
            token="token",
            tooling_evidence=self.tooling,
            tooling_public_key=self.tooling_key,
            java_executable=self.java,
            policy_revision="9" * 40,
            required_trust_domain="release",
        )
        arguments.update(changes)
        stack = ExitStack()
        stack.enter_context(patch.object(workflow.product_reuse, "capture_sdk_ios_package_upload",
                                         side_effect=self.capture_package))
        stack.enter_context(patch.object(workflow.product_reuse, "_validate_plan",
                                         side_effect=self.validate_plan))
        stack.enter_context(patch.object(workflow.product_reuse, "_consumer",
                                         side_effect=lambda *_: {"producer": self.consumer_producer}))
        stack.enter_context(patch.object(workflow, "git_product_versions",
                                         return_value={"runtime-release": "0.2.0", "sdk": "0.8.0"}))
        stack.enter_context(patch.object(workflow, "sdk_runtime_source", return_value=None))
        stack.enter_context(patch.object(workflow.product_reuse, "capture_sdk_inputs_upload",
                                         side_effect=self.capture_sdk))
        stack.enter_context(patch.object(workflow, "verified_apple_original_inputs",
                                         side_effect=self.signed_inputs))
        stack.enter_context(patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.gate))
        self.addCleanup(stack.close)
        context = workflow.verified_original_ios_package(self.plan, self.receipt_path, **arguments)
        return context

    def prepare_retained(self):
        self.retained_package = self.root / "retained-package"
        snapshot_regular_tree(self.upload, self.retained_package, allow_empty=True)
        self.retained_sdk = self.root / "retained-sdk"
        self.capture_sdk(self.plan, self.retained_sdk, expected_source="current-runtime",
                         artifact_id=811, artifact_sha256="sha256:" + "8" * 64)
        sdk_original = self.retained_sdk / "original"
        sdk_original.mkdir()
        (self.retained_sdk / "sdk").rename(sdk_original / "sdk-inputs")
        (self.retained_sdk / "authority").rename(sdk_original / "sdk-inputs/authority")
        (self.retained_sdk / "transport.bin").rename(sdk_original / "sdk-inputs/transport.bin")
        nested_plan = sdk_original / "runtime-capture/plan/impact-plan.json"
        nested_plan.parent.mkdir(parents=True)
        nested_plan.write_bytes(self.plan.read_bytes())
        self.archive_retained(self.retained_sdk)
        sdk_digest = sha256_file(self.retained_sdk / "transport.zip")
        (self.retained_sdk / "original-package-receipt.json").write_bytes(self.receipt_bytes)
        write_canonical_json(self.retained_sdk / "capture-transport.json", {
            "artifact": {"id": 811, "digest": sdk_digest,
                         "name": f"codex-agent-sdk-inputs-{self.producer['tree']}-attempt-2"},
            "captureProducer": self.producer, "observed": [], "sdkRuntimeSource": "current-runtime",
            "packageReceiptSha256": sha256_bytes(self.receipt_bytes),
        })
        descriptor_path = self.retained_package / "original/apple-package-execution.json"
        descriptor = json.loads(descriptor_path.read_bytes())
        descriptor["sdkInputsArtifact"]["artifactSha256"] = sdk_digest
        write_canonical_json(descriptor_path, descriptor)
        self.archive_retained(self.retained_package)
        write_canonical_json(self.retained_package / "capture-transport.json", {
            "artifact": {"id": 701, "digest": sha256_file(self.retained_package / "transport.zip"),
                "name": f"codex-agent-sdk-worker-sdk-ios-package-ios-{self.receipt['buildKey'].removeprefix('sha256:')}-{self.producer['tree']}-attempt-2"},
            "captureProducer": self.producer, "observed": [], "packageReceiptSha256": sha256_bytes(self.receipt_bytes),
        })
        self.events.clear()
        self.private_paths.clear()

    def archive_retained(self, capture):
        plan = capture / "plan/impact-plan.json"
        plan.parent.mkdir(exist_ok=True)
        plan.write_bytes(self.plan.read_bytes())
        with zipfile.ZipFile(capture / "transport.zip", "w") as archive:
            for record in regular_file_inventory(capture / "original", allow_empty=True):
                name = record["relativePath"]
                archive.write(capture / "original" / name, name)

    @contextmanager
    def retained_context(self):
        def validate(path, repository, **arguments):
            self.last_original = path.parent.parent
            self.assertEqual(self.plan.read_bytes(), path.read_bytes())
            return self.validate_plan(path, repository, **arguments)

        @contextmanager
        def signed(capture, **arguments):
            sdk = capture / "original/sdk-inputs"
            self.sdk_paths = {"directory": sdk, "authority": sdk / "authority",
                              "metadata": sdk / "authority/metadata.json", "keys": sdk / "authority/keys"}
            with self.signed_inputs(capture, **arguments) as value:
                yield value

        with ExitStack() as stack:
            network = []
            for name in ("capture_sdk_ios_package_upload", "capture_sdk_inputs_upload", "api_json", "download_artifact"):
                network.append(stack.enter_context(patch.object(workflow.product_reuse, name,
                    side_effect=AssertionError("retained content replay must not access network"))))
            stack.enter_context(patch.object(workflow.product_reuse, "_validate_plan", side_effect=validate))
            stack.enter_context(patch.object(workflow.product_reuse, "_consumer",
                side_effect=lambda *_: {"producer": self.consumer_producer}))
            stack.enter_context(patch.object(workflow, "git_product_versions",
                return_value={"runtime-release": "0.2.0", "sdk": "0.8.0"}))
            stack.enter_context(patch.object(workflow, "sdk_runtime_source", return_value=None))
            stack.enter_context(patch.object(workflow, "verified_apple_original_inputs", side_effect=signed))
            stack.enter_context(patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.gate))
            try:
                with workflow.verified_retained_ios_package(self.plan, self.receipt_path,
                        package_capture=self.retained_package, sdk_capture=self.retained_sdk,
                        keyring=self.keyring, keys_directory=self.keys, repository_root=self.root,
                        tooling_evidence=self.tooling, tooling_public_key=self.tooling_key, java_executable=self.java,
                        policy_revision="9" * 40, required_trust_domain="release") as value:
                    yield value
            finally:
                for operation in network:
                    operation.assert_not_called()

    def test_restores_exact_originals_runs_full_gate_inside_signed_context_and_cleans_up(self):
        with self.original_context() as value:
            self.last_original = value["original"]
            self.assertEqual(self.receipt, value["receipt"])
            self.assertEqual(self.receipt_bytes, value["receiptBytes"])
            self.assertEqual(self.receipt_bytes, value["receiptPath"].read_bytes())
            self.assertEqual(value["original"].parent, value["packageCapture"])
            self.assertEqual(value["sdk"]["directory"].parent, value["sdkCapture"])
            self.assertTrue(value["packageCapture"].is_dir())
            self.assertTrue(value["sdkCapture"].is_dir())
            self.assertEqual(self.compatibility_bytes,
                             (value["stage"] / "outputs/evidence/sdk-compatibility.json").read_bytes())
            self.assertEqual({"synthetic": "authenticated runtime input"}, value["runtime"])
            self.assertEqual(["package-capture", "sdk-capture", "signed-enter", "full-gate"], self.events)
            stage = value["stage"]
        self.assertEqual(
            ["package-capture", "sdk-capture", "signed-enter", "full-gate", "signed-exit", "signed-closed"],
            self.events,
        )
        self.assertFalse(stage.exists())
        self.assertTrue(all(not path.exists() for path in self.private_paths))

    def test_full_gate_failure_never_yields_or_publishes(self):
        self.gate_failure = True
        with self.assertRaisesRegex(ValueError, "full original package rejection"):
            with self.original_context():
                self.fail("rejected original package yielded")
        self.assertIn("signed-closed", self.events)
        self.assertTrue(all(not path.exists() for path in self.private_paths))

    def test_authenticated_sdk_metadata_mismatch_rejects_before_full_gate(self):
        self.metadata_mismatch = True
        with self.assertRaisesRegex(ValueError, "Contract predecessor differs"):
            with self.original_context():
                self.fail("cross-paired Contract metadata yielded")
        self.assertNotIn("full-gate", self.events)
        self.assertTrue(all(not path.exists() for path in self.private_paths))

    def test_signed_contract_binary_mismatch_rejects_before_full_gate(self):
        self.binary_mismatch = True
        with self.assertRaisesRegex(ValueError, "Contract binary differs"):
            with self.original_context():
                self.fail("cross-paired signed Contract binary yielded")
        self.assertNotIn("full-gate", self.events)
        self.assertTrue(all(not path.exists() for path in self.private_paths))

    def test_historical_plan_phase_plan_and_descriptor_mismatches_reject(self):
        for mutation in ("producer", "phase-plan", "descriptor"):
            self.events.clear()
            self.consumer_producer = self.producer
            self.upload_mutation = None
            if mutation == "producer":
                self.consumer_producer = {**self.producer, "runAttempt": 1}
            else:
                self.upload_mutation = mutation
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with self.original_context():
                    self.fail("mismatched original package yielded")
            self.assertNotIn("full-gate", self.events)

    def test_context_exit_capture_policy_and_in_memory_receipt_mutations_reject(self):
        policy_bytes = self.keyring.read_bytes()
        for mutation in ("capture", "sdk-capture", "policy", "receipt"):
            self.events.clear()
            self.context_exit_mutation = mutation if mutation != "receipt" else None
            try:
                with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    ValueError, "recovery inputs changed during use",
                ):
                    with self.original_context() as value:
                        if mutation == "receipt":
                            value["receipt"]["result"] = "failure"
                self.assertTrue(all(not path.exists() for path in self.private_paths))
            finally:
                self.keyring.write_bytes(policy_bytes)

    def test_retained_captures_use_same_full_gate_without_network_and_remain_private(self):
        self.prepare_retained()
        before = {path: regular_file_inventory(path, allow_empty=True)
                  for path in (self.retained_package, self.retained_sdk)}
        with self.retained_context() as value:
            self.assertEqual(self.receipt_bytes, value["receiptBytes"])
            self.assertEqual(self.receipt_bytes, value["receiptPath"].read_bytes())
            self.assertNotEqual(self.retained_package, value["packageCapture"])
            self.assertNotEqual(self.retained_sdk, value["sdkCapture"])
            self.assertEqual(before[self.retained_package], regular_file_inventory(value["packageCapture"], allow_empty=True))
            self.assertEqual(before[self.retained_sdk], regular_file_inventory(value["sdkCapture"], allow_empty=True))
            self.assertEqual(["signed-enter", "full-gate"], self.events)
            private = value["stage"].parent
        self.assertFalse(private.exists())
        self.assertEqual(["signed-enter", "full-gate", "signed-exit", "signed-closed"], self.events)
        self.assertEqual(before, {path: regular_file_inventory(path, allow_empty=True) for path in before})

    def test_retained_original_private_and_context_exit_mutation_reject(self):
        self.prepare_retained()
        for mutation in ("original-package", "original-sdk", "private-package", "private-sdk", "context-exit"):
            self.context_exit_mutation = "sdk-capture" if mutation == "context-exit" else None
            originals = {self.retained_package / "original/apple-package-execution.json":
                         (self.retained_package / "original/apple-package-execution.json").read_bytes(),
                         self.retained_sdk / "transport.zip": (self.retained_sdk / "transport.zip").read_bytes()}
            try:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    with self.retained_context() as value:
                        paths = {"original-package": self.retained_package / "original/apple-package-execution.json",
                                 "original-sdk": self.retained_sdk / "transport.zip",
                                 "private-package": value["packageCapture"] / "original/apple-package-execution.json",
                                 "private-sdk": value["sdkCapture"] / "transport.zip"}
                        if mutation in paths:
                            paths[mutation].write_bytes(b"late original mutation\n")
                        private = value["stage"].parent
                self.assertFalse(private.exists())
            finally:
                for path, raw in originals.items():
                    path.write_bytes(raw)

    def test_retained_mode_still_rejects_full_semantic_gate_failure(self):
        self.prepare_retained()
        self.gate_failure = True
        with self.assertRaisesRegex(ValueError, "full original package rejection"):
            with self.retained_context():
                self.fail("retained input bypassed the existing full gate")
        self.assertIn("signed-closed", self.events)

    def test_retained_sdk_transport_receipt_plan_and_archive_mismatches_reject_before_gate(self):
        self.prepare_retained()
        transport_path = self.retained_sdk / "capture-transport.json"
        for mutation in ("id", "digest", "source", "producer", "receipt-digest", "receipt", "plan", "original", "archive"):
            paths = [transport_path, self.retained_sdk / "original-package-receipt.json",
                     self.retained_sdk / "plan/impact-plan.json", self.retained_sdk / "transport.zip",
                     self.retained_sdk / "original/sdk-inputs" / REQUEST_NAME]
            baseline = {path: path.read_bytes() for path in paths}
            self.events.clear()
            try:
                transport = json.loads(transport_path.read_bytes())
                if mutation == "id":
                    transport["artifact"]["id"] += 1
                elif mutation == "digest":
                    transport["artifact"]["digest"] = "sha256:" + "0" * 64
                elif mutation == "source":
                    transport["sdkRuntimeSource"] = "released-default"
                elif mutation == "producer":
                    transport["captureProducer"]["runAttempt"] = 1
                elif mutation == "receipt-digest":
                    transport["packageReceiptSha256"] = "sha256:" + "0" * 64
                else:
                    target = {"receipt": paths[1], "plan": paths[2], "archive": paths[3], "original": paths[4]}[mutation]
                    target.write_bytes(target.read_bytes() + b"changed")
                write_canonical_json(transport_path, transport)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    with self.retained_context():
                        self.fail("inconsistent retained SDK capture yielded")
                self.assertNotIn("signed-enter", self.events)
                self.assertNotIn("full-gate", self.events)
            finally:
                for path, raw in baseline.items():
                    path.write_bytes(raw)

    def test_retained_package_zip_and_materialized_tree_must_agree(self):
        self.prepare_retained()
        path = self.retained_package / "original/inputs/producer.json"
        value = json.loads(path.read_bytes())
        value["runAttempt"] = 1
        write_canonical_json(path, value)
        with self.assertRaisesRegex(ValueError, "content differs from its original archive"):
            with self.retained_context():
                self.fail("materialized package drift yielded")
        self.assertNotIn("signed-enter", self.events)


if __name__ == "__main__":
    unittest.main()

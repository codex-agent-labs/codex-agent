"""Real original shards; mocked CI, Git/signature and semantic gate boundaries.

These prove composition and lifetime only, never real compiler/host admission.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_maven_original as original
from ci.tests.product_chain_support import write_receipt
from products.inventory import canonical_json_bytes, snapshot_regular_tree, write_canonical_json, sha256_file
from products.receipt import write_output_manifest
from products.restore import finalize_phase_object


class MavenOriginalTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "repository"
        self.root.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "workflowPath": ".github/workflows/product-validation.yml",
            "runId": 10, "runAttempt": 1, "pullRequest": 2}
        self.contracts = {phase: self.record("contract", "contract", phase, "common")
                          for phase in ("binary", "package", "validation", "metadata")}
        self.auth = self.base / "contract-proof"
        self.auth.mkdir()
        stem = "codex-agent-contract-0.8.7"
        self.evidence = {"stageRoot": str(self.contracts["metadata"]["stage"]),
            "phaseReceipt": str(self.contracts["metadata"]["receiptPath"]),
            "attestation": str(self.auth / (stem + ".attestation.json")),
            "attestationSignature": str(self.auth / (stem + ".attestation.sig")),
            "publicKey": str(self.auth / "public-key.pub"),
            "expectedTrustDomain": "release", "keyring": None, "keysDirectory": None}
        for name in ("attestation", "attestationSignature", "publicKey"):
            Path(self.evidence[name]).write_bytes(("mocked original " + name).encode())
        receipts = self.auth / "execution-closure/receipts"
        receipts.mkdir(parents=True)
        for phase, record in self.contracts.items():
            (receipts / (phase + ".json")).write_bytes(record["receiptPath"].read_bytes())
        self.keyring = self.base / "caller-ring.json"
        self.keyring.write_bytes(b"independent caller public policy")
        self.keys = self.base / "caller-keys"
        self.keys.mkdir()
        (self.keys / "public.pub").write_bytes(b"public key")
        self.archive = self.base / "runtime.tar.gz"
        self.archive.write_bytes(b"original Android pinned archive")
        self.context = {"repositoryRoot": "/old/checkout", "workerRoot": "/old/checkout/build/upload"}
        self.events, self.exit_failure = [], False
        self.capture = self.enterContext(patch.object(original, "capture_sdk_maven_upload", side_effect=self.capture_upload))
        self.transport = self.enterContext(patch.object(original, "verify_retained_sdk_phase_upload"))
        self.historical = self.enterContext(patch.object(original.product_reuse, "_validate_plan",
            return_value={"event": "pull_request", "remoteBuildAuthorized": True}))
        self.enterContext(patch.object(original.product_reuse, "_consumer", return_value={"producer": self.producer}))
        self.enterContext(patch.object(original, "git_product_versions", return_value={"sdk": "0.8.7",
            "contract": "0.8.7", "runtime-release": "0.8.7", "runtime-compatibility": "0.8.0"}))
        self.projection = self.enterContext(patch.object(original, "_contract_projection_from_request"))
        self.replan = self.enterContext(patch.object(original, "_verify_plan"))
        self.binary_gate = self.enterContext(patch.object(original, "verify_sdk_maven_binary_content"))
        self.package_gate = self.enterContext(patch.object(original, "verify_sdk_package_inputs", side_effect=self.package_content))
        self.enterContext(patch.object(original, "sdk_runtime_source", return_value="current-runtime"))
        self.enterContext(patch.object(original.product_reuse, "_verify_retained_sdk_upload_archive"))
        self.joined = self.enterContext(patch.object(original, "verified_apple_original_inputs", side_effect=self.sdk_inputs))
        self.pins = self.enterContext(patch.object(original, "git_regular_blob_bytes", return_value=(
            "codexAgent.codexVersion=0.149.0\n" + "codexAgent.codexArchiveSha256=" +
            sha256_file(self.archive).removeprefix("sha256:") + "\n").encode()))

    def record(self, product, component, phase, target):
        directory = self.base / (component + "-" + phase)
        stage = directory / "stage"
        name = "codex-agent-contract-0.8.7.zip" if product == "contract" and phase == "metadata" else "artifact.bin"
        path = stage / "outputs" / name
        path.parent.mkdir(parents=True)
        path.write_bytes((component + "-" + phase).encode())
        kind = "contract-bundle" if name.endswith(".zip") else "fixture"
        manifest = write_output_manifest(stage, product, component, phase, target, "0.8.7", {kind: "outputs"})
        receipt_path = directory / "phase-receipt.json"
        receipt = write_receipt(receipt_path, product=product, component=component, phase=phase,
            target=target, version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"],
            upstream=[], context={"producer": self.producer})
        return {"stage": stage, "receiptPath": receipt_path, "receipt": receipt}

    def prepare(self, component="sdk-core", phase="binary"):
        self.component, self.phase = component, phase
        target = "common" if component == "sdk-core" else "android"
        self.binary = self.record("sdk", component, "binary", target)
        self.selected = self.binary if phase == "binary" else self.record("sdk", component, phase, target)
        self.receipt_path, self.receipt = self.selected["receiptPath"], self.selected["receipt"]
        self.upload = self.base / "authenticated-capture"
        self.upload.mkdir()
        self.original = self.upload / "original"
        self.original.mkdir()
        (self.upload / "plan").mkdir()
        (self.upload / "plan/impact-plan.json").write_bytes(self.plan.read_bytes())
        (self.upload / "transport.zip").write_bytes(b"opaque observed upload")
        (self.upload / "capture-transport.json").write_bytes(b"{}\n")
        inputs = self.original / ("inputs/predecessors" if phase == "binary" else "inputs")
        inputs.mkdir(parents=True)
        for record in [*self.contracts.values(), *([self.binary] if phase == "package" else [])]:
            value = record["receipt"]
            directory = inputs / "-".join(value[name] for name in ("product", "component", "phase", "target"))
            snapshot_regular_tree(record["stage"], directory / "stage")
            (directory / "phase-receipt.json").write_bytes(record["receiptPath"].read_bytes())
        selection = self.original / "selection"
        selection.mkdir()
        (selection / "impact-plan.json").write_bytes(self.plan.read_bytes())
        for directory in (selection, inputs):
            write_canonical_json(directory / "phase-plan.json", {name: self.receipt[name] for name in original.PHASE_PLAN_KEYS})
            write_canonical_json(directory / "producer.json", self.producer)
        finalize_phase_object(stage_root=self.selected["stage"],
            phase_plan={name: self.receipt[name] for name in original.PHASE_PLAN_KEYS}, producer=self.producer,
            product_version="0.8.7", trust_domain="development", destination=self.original / "shard")
        stem = "codex-agent-contract-0.8.7"
        if phase == "binary":
            handoff = self.original / "inputs/contract-input"
            snapshot_regular_tree(self.auth, handoff)
            (handoff / (stem + ".zip")).write_bytes((self.contracts["metadata"]["stage"] / "outputs" / (stem + ".zip")).read_bytes())
            if component == "sdk-android":
                archive = self.original / "android-original" / self.archive.name
                archive.parent.mkdir()
                archive.write_bytes(self.archive.read_bytes())
        else:
            self.context["compatibilityRequest"] = "/old/sdk-inputs/sdk-compatibility-request.json"
            retained = self.original / "binary-contract-original"
            snapshot_regular_tree(self.contracts["metadata"]["stage"], retained / "stage")
            snapshot_regular_tree(self.auth, retained / "evidence")
            (retained / "evidence/phase-receipt.json").write_bytes(self.contracts["metadata"]["receiptPath"].read_bytes())
            write_canonical_json(retained / "invocation.json", self.evidence)
            sdk = self.original / "sdk-inputs-original"
            (sdk / "plan").mkdir(parents=True)
            (sdk / "plan/impact-plan.json").write_bytes(self.plan.read_bytes())
            (sdk / "transport.zip").write_bytes(b"opaque original SDK ZIP")
            (sdk / "original").mkdir()
            write_canonical_json(sdk / "capture-transport.json", {"artifact": {
                "id": 1, "digest": "sha256:" + "c" * 64,
                "name": f"codex-agent-sdk-inputs-{self.producer['tree']}-attempt-1"},
                "captureProducer": self.producer, "observed": [], "sdkRuntimeSource": "current-runtime"})
        worker = self.original / "worker"
        worker.mkdir()
        fields = {"codexAgent." + name: self.receipt[name] for name in ("product", "component", "phase", "target")}
        fields.update({"codexAgent.sdkVersion": "0.8.7", "codexAgent.candidateCommit": self.producer["commit"],
                       "codexAgent.candidateTree": self.producer["tree"]})
        origin = Path(self.context["workerRoot"])
        if phase == "binary":
            handoff = origin / "inputs/contract-input"
            fields.update({"codexAgent.contractVersion": "0.8.7",
                "codexAgent.contractMetadataReceipt": str(origin / "inputs/predecessors/contract-contract-metadata-common/phase-receipt.json"),
                "codexAgent.contractPayload": str(handoff / (stem + ".zip")),
                "codexAgent.contractAttestation": str(handoff / (stem + ".attestation.json")),
                "codexAgent.contractAttestationSignature": str(handoff / (stem + ".attestation.sig")),
                "codexAgent.contractPublicKey": str(handoff / "public-key.pub")})
            if component == "sdk-android":
                fields["codexAgent.codexArchiveFile"] = str(origin / "android-original" / self.archive.name)
        else:
            key = "sdkCoreBinaryStageRoot" if component == "sdk-core" else "sdkAndroidBinaryStageRoot"
            fields["codexAgent." + key] = str(origin / "inputs" / f"sdk-{component}-binary-{target}" / "stage")
            fields["codexAgent.sdkCompatibilityRequest"] = self.context["compatibilityRequest"]
        command = original.product_reuse._runtime_worker_command(Path("/old/checkout/gradlew"), fields, {},
                                                                  build_directory=".", platform_name="posix")
        write_canonical_json(worker / "execution.json", {"schemaVersion": 1, "producer": self.producer,
            "buildKey": self.receipt["buildKey"], "command": command, "returnCode": 0, "launchError": None, "elapsedNs": 10})
        (worker / "gradle.log").write_bytes(b"")

    def capture_upload(self, plan, destination, **kwargs):
        self.assertEqual(self.receipt_path.read_bytes(), kwargs["receipt_path"].read_bytes())
        self.assertEqual("caller-token", kwargs["token"])
        snapshot_regular_tree(self.upload, destination, allow_empty=True)

    @contextmanager
    def sdk_inputs(self, capture, **kwargs):
        self.events.append("sdk-enter")
        self.assertEqual(self.keyring, kwargs["keyring"])
        self.assertEqual(self.keys, kwargs["keys_directory"])
        self.assertEqual(self.producer["commit"], kwargs["selection_revision"])
        yield {"sdk": {"directory": capture / "original", "arguments": {
            "contract_metadata_receipt": self.contracts["metadata"]["receiptPath"],
            "contract_attestation": Path(self.evidence["attestation"])}}}
        self.events.append("sdk-exit")
        if self.exit_failure:
            raise ValueError("SDK original context exit rejected")

    def package_content(self, repository, stage, receipt, request, **kwargs):
        self.events.append("package-gate")
        self.assertEqual(self.evidence, kwargs["binary_contract_evidence"])
        self.assertEqual(self.binary["receiptPath"].read_bytes(), kwargs["binary_receipt_path"].read_bytes())
        self.assertEqual(self.receipt_path.read_bytes(), receipt.read_bytes())
        return deepcopy(self.receipt), receipt.read_bytes()

    def call(self, retained=False, **changes):
        kwargs = dict(binary_contract_evidence=self.evidence, original_context=self.context,
                      repository_root=self.root, environ={"GITHUB_RUN_ID": "999"})
        if self.phase == "package":
            kwargs.update(keyring=self.keyring, keys_directory=self.keys)
        if (self.component, self.phase) == ("sdk-android", "binary"):
            kwargs["android_runtime_archive"] = self.archive
        kwargs.update(changes)
        if retained:
            return original.verified_retained_maven_phase(self.plan, self.receipt_path,
                                                         capture_root=self.upload, **kwargs)
        return original.verified_original_maven_phase(self.plan, self.receipt_path, artifact_id=1,
            artifact_sha256="sha256:" + "c" * 64, trusted_workflow_sha="d" * 40, token="caller-token", **kwargs)

    def test_all_four_phases_preserve_receipts_and_hold_private_paths(self):
        for component in ("sdk-core", "sdk-android"):
            for phase in ("binary", "package"):
                with self.subTest(component=component, phase=phase):
                    fixture = MavenOriginalTest(methodName="runTest")
                    fixture.setUp()
                    try:
                        fixture.prepare(component, phase)
                        with fixture.call() as result:
                            stage = result["stage"]
                            self.assertEqual(fixture.receipt_path.read_bytes(), result["receiptBytes"])
                            self.assertEqual(fixture.receipt, result["receipt"])
                            self.assertTrue(stage.exists())
                            if phase == "package":
                                self.assertEqual(["sdk-enter", "package-gate"], fixture.events)
                        self.assertFalse(stage.exists())
                        fixture.capture.assert_called_once()
                        fixture.transport.assert_called_once()
                        if phase == "binary":
                            fixture.replan.assert_called_once()
                            fixture.binary_gate.assert_called_once()
                        else:
                            self.assertEqual("sdk-exit", fixture.events[-1])
                    finally:
                        fixture.doCleanups()

    def test_retained_mode_does_not_observe_or_trust_uploaded_invocation(self):
        self.prepare(phase="package")
        with self.call(retained=True):
            pass
        self.capture.assert_not_called()
        self.assertIs(self.package_gate.call_args.kwargs["binary_contract_evidence"], self.evidence)
        self.assertNotEqual(self.producer["runId"], 999)

    def test_fixed_command_requires_independent_original_context(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "fixed offline command"), self.call(
                original_context={**self.context, "repositoryRoot": "/old"}):
            pass
        self.binary_gate.assert_not_called()
        path = self.original / "worker/execution.json"
        value = original._json(path)
        value["command"].remove("--offline")
        write_canonical_json(path, value)
        with self.assertRaisesRegex(ValueError, "fixed offline command"), self.call():
            pass

    def test_caller_contract_and_android_archive_cannot_be_replaced(self):
        self.prepare("sdk-android")
        self.archive.write_bytes(b"unrelated archive")
        with self.assertRaisesRegex(ValueError, "archive differs"), self.call():
            pass
        self.binary_gate.assert_not_called()
        self.archive.write_bytes(b"original Android pinned archive")
        Path(self.evidence["publicKey"]).write_bytes(b"different caller proof")
        with self.assertRaisesRegex(ValueError, "handoff differs"), self.call():
            pass

    def test_git_archive_pin_and_original_replan_failure_reject(self):
        self.prepare("sdk-android")
        self.pins.return_value = b"codexAgent.codexVersion=0.149.0\ncodexAgent.codexArchiveSha256=" + b"0" * 64 + b"\n"
        with self.assertRaisesRegex(ValueError, "immutable Git pin"), self.call():
            pass
        self.binary_gate.assert_not_called()

    def test_historical_identity_and_source_key_fail_before_content(self):
        self.prepare()
        self.historical.return_value["remoteBuildAuthorized"] = False
        with self.assertRaisesRegex(ValueError, "authorized producer"), self.call():
            pass
        self.historical.return_value["remoteBuildAuthorized"] = True
        self.replan.side_effect = ValueError("original Git key differs")
        with self.assertRaisesRegex(ValueError, "original Git key differs"), self.call():
            pass
        self.binary_gate.assert_not_called()

    def test_yielded_capture_receipt_and_caller_mutation_are_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as result:
            (result["original"] / "worker/gradle.log").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as result:
            result["receipt"]["producer"]["runId"] += 1
        with self.assertRaisesRegex(ValueError, "changed"), self.call():
            self.context["workerRoot"] = "/old/checkout/changed"

    def test_package_context_exit_failure_and_nested_original_mutation_reject(self):
        self.prepare(phase="package")
        self.exit_failure = True
        with self.assertRaisesRegex(ValueError, "context exit rejected"), self.call():
            pass
        self.exit_failure = False
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as result:
            (result["original"] / "sdk-inputs-original/transport.zip").write_bytes(b"replaced")

    def test_secret_or_wrong_phase_policy_fails_before_capture(self):
        self.prepare()
        for changes in ({"keyring": self.keyring, "keys_directory": self.keys},
                        {"android_runtime_archive": self.archive},
                        {"environ": {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError), self.call(**changes):
                pass
        self.capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Native validation controller controls, not host or signature acceptance.

Election, authenticated inputs/upload, package verification and the final full
carrier gate are explicit seams. Original inventories and shard finalization
are real; the leaf tests execute only a mocked Gradle process.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci import sdk_native_validation_workflow as workflow
from ci.tests import test_sdk_native_package_execution as fixture
from ci.tests import test_sdk_native_phase as leaf_fixture
from ci.tests.product_chain_support import write_receipt
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from products.receipt import compute_build_key, write_output_manifest
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import verify_phase_shard


class SdkNativeValidationExecutionTest(unittest.TestCase):
    tearDown = fixture.SdkNativePackageExecutionTest.tearDown
    name = staticmethod(fixture.SdkNativePackageExecutionTest.name)
    capture = fixture.SdkNativePackageExecutionTest.capture
    fixture = fixture.SdkNativePackageExecutionTest.fixture

    def setUp(self):
        fixture.SdkNativePackageExecutionTest.setUp(self)
        self.ready = {**self.ready, "phase": "validation", "target": "linux-x64"}
        self.ready["buildKey"] = compute_build_key(**{name: self.ready[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        self.selection["consumers"] = [{name: self.ready[name] for name in ("product", "component", "phase", "target")}]
        self.package_stage = self.root / "original-sdk-package/stage"
        (self.package_stage / "outputs").mkdir(parents=True)
        (self.package_stage / "outputs/package.bin").write_bytes(b"original SDK package\n")
        manifest = write_output_manifest(self.package_stage, "sdk", "python", "package", "desktop", "0.3.0", {"package": "outputs"})
        self.package_receipt_path = self.package_stage.parent / "phase-receipt.json"
        self.package_receipt = write_receipt(self.package_receipt_path, product="sdk", component="python",
            phase="package", target="desktop", version="0.3.0", version_identity="0.3.0",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.package_before = regular_file_inventory(self.package_stage.parent)
        policy = {"schemaVersion": 1, "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                  "trustDomain": "release", "activeKey": None, "retiredKeys": []}
        write_canonical_json(self.arguments["keyring"], policy)
        self.arguments["keys_directory"].mkdir()
        tooling = self.root / "tooling"
        tooling.mkdir()
        (tooling / "untrusted-fixture").write_bytes(b"explicit full-gate seam")
        public, java = self.root / "tooling.pub", self.root / "java"
        public.write_bytes(b"synthetic public key gate seam")
        java.write_bytes(b"synthetic Java gate seam")
        self.arguments.update(target="linux-x64", expected_build_key=self.ready["buildKey"],
            tooling_evidence=tooling, tooling_public_key=public, java_executable=java,
            policy_revision="a" * 40, required_trust_domain="development")
        self.tooling = {"evidence": str(tooling), "publicKey": str(public), "javaExecutable": str(java),
                        "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}
        self.policy_bytes = self.arguments["keyring"].read_bytes()

    def inspect(self, *args, **kwargs):
        self.assertEqual(self.tooling, kwargs.pop("sdk_validation_tooling"))
        return fixture.SdkNativePackageExecutionTest.inspect(self, *args, **kwargs)

    @contextmanager
    def verified(self, *args, **kwargs):
        self.assertEqual((self.plan_path, self.discovery, self.state), args)
        self.assertEqual(self.tooling, kwargs["sdk_validation_tooling"])
        self.events.append("enter")
        self.live = True
        try:
            yield self.verified_inputs
            self.events.append("exit-check")
            if self.failure == "late-context": raise ValueError("late authenticated input rejection")
            changed = {
                "late-plan": self.plan_path,
                "late-state": self.preparation_state / "control.json",
                "late-policy": self.arguments["keyring"],
                "late-input": self.destination / "inputs/producer.json",
                "late-runtime": self.destination / f"runtime-stages/{NATIVE_TARGETS[0]}/package/outputs/original",
                "late-capture": self.capture_path / "original/staged-sdks/sdk",
                "late-stage": self.result["stage"] / "outputs/capability/raw.log",
                "late-candidate": self.candidate_path / "phase-receipt.json",
                "late-carrier": self.carrier_path / "carrier.json",
            }
            if self.failure in changed: changed[self.failure].write_bytes(b"late mutation\n")
            self.events.append("exited")
        finally:
            self.live = False

    def materialize(self, plan, discovery, state, identity, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("materialize")
        self.assertEqual(PhaseInstanceId("sdk", "python", "validation", "linux-x64"), identity)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        self.assertEqual(self.tooling, kwargs["sdk_validation_tooling"])
        originals = {**self.original_paths, fixture.fixture.CONTRACT: self.contract,
            PhaseInstanceId("sdk", "python", "package", "desktop"): {
                "stage": self.package_stage, "receiptPath": self.package_receipt_path}}
        for original_identity, value in originals.items():
            directory = destination / self.name(original_identity)
            snapshot_regular_tree(value["stage"], directory / "stage")
            (directory / "phase-receipt.json").write_bytes(value["receiptPath"].read_bytes())
        write_canonical_json(destination / "producer.json", self.producer)
        write_canonical_json(destination / "phase-plan.json", self.ready)
        return self.ready

    def package_gate(self, repository, stage, receipt, request, **kwargs):
        self.assertTrue(self.live)
        self.events.append("package-gate")
        self.assertEqual(self.root, repository)
        self.assertEqual(self.package_before, regular_file_inventory(stage.parent))
        self.assertEqual(self.package_receipt_path.read_bytes(), receipt.read_bytes())
        self.assertEqual(self.sdk / workflow.REQUEST_NAME, request)
        self.assertEqual({"runtime_stage_root": self.destination / "runtime-stages",
            "staged_sdks": self.capture_path / "original/staged-sdks"}, kwargs)
        if self.failure == "package-gate": raise ValueError("original package content rejected")
        if self.failure == "package-plan": self.ready["buildKey"] = "sha256:" + "f" * 64
        if self.failure == "package-producer": self.elected_producer["runAttempt"] = 3
        raw = receipt.read_bytes()
        return load_canonical_json_bytes(raw), raw + b"wrong" if self.failure == "package-pairing" else raw

    def worker(self, ready, **kwargs):
        self.assertTrue(self.live)
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual("0.3.0", kwargs["sdk_version"])
        self.assertEqual(self.package_receipt, kwargs["package"]["receipt"])
        self.assertEqual(self.capture_path / "original/staged-sdks", kwargs["staged_sdks"])
        self.assertEqual(self.sdk / workflow.REQUEST_NAME, kwargs["compatibility_request"])
        for path in (self.plan_path, self.discovery, self.state, self.preparation_state,
                     self.arguments["tooling_evidence"], self.arguments["keyring"],
                     self.arguments["java_executable"], self.sdk, self.capture_path,
                     self.destination / "inputs"):
            self.assertIn(path, kwargs["protected_inputs"])
        for identity, record in self.original_paths.items():
            restored = kwargs["predecessor"](identity.product, identity.component, identity.phase, identity.target)
            self.assertEqual(self.receipt_bytes[identity], restored["receiptPath"].read_bytes())
            self.assertEqual(regular_file_inventory(record["stage"]), regular_file_inventory(restored["stage"]))
        if self.failure == "worker": raise ValueError("actual worker failed")
        stage = self.destination / "synthetic-stage"
        (stage / "outputs/capability").mkdir(parents=True)
        (stage / "outputs/capability/raw.log").write_bytes(b"synthetic raw validation\xff\x00\n")
        write_output_manifest(stage, "sdk", "python", "validation", "linux-x64", "0.3.0",
                              {"native-wrapper-capability": "outputs/capability"})
        self.result = {"stage": stage, "diagnostics": kwargs["destination"], "outputInventory": regular_file_inventory(stage)}
        return self.result

    def validation_gate(self, records, source, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("validation-gate")
        self.assertFalse((self.destination / "shard").exists())
        self.assertFalse(source.is_relative_to(self.root))
        record, = records
        self.assertEqual(("python", "linux-x64"), (record["component"], record["target"]))
        self.assertTrue(all(not Path(record[name]).is_absolute() and ".." not in Path(record[name]).parts
            for name in ("packageStage", "runtimeStages", "stagedSdks", "validationStage",
                         "packageReceipt", "validationReceipt", "compatibilityRequest")))
        self.assertEqual({"repository": self.root, "policy_revision": "a" * 40,
            "tooling": {"evidence": str(self.arguments["tooling_evidence"]),
                "publicKey": str(self.arguments["tooling_public_key"]),
                "javaExecutable": str(self.arguments["java_executable"]),
                "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}}, kwargs)
        self.assertEqual(self.package_receipt_path.read_bytes(), (source / record["packageReceipt"]).read_bytes())
        self.assertEqual(self.sdk.joinpath(workflow.REQUEST_NAME).read_bytes(),
                         (source / record["compatibilityRequest"]).read_bytes())
        self.gate_receipt = (source / record["validationReceipt"]).read_bytes()
        self.assertEqual(record["receiptSha256"], sha256_bytes(self.gate_receipt))
        self.candidate_path = destination.parent / "shard"
        self.assertEqual(self.gate_receipt, (self.candidate_path / "phase-receipt.json").read_bytes())
        if self.failure == "validation-gate": raise ValueError("full matcher rejected")
        destination.mkdir()
        (destination / "carrier.json").write_bytes(canonical_json_bytes(records))
        self.carrier_path = destination
        if self.failure == "validation-candidate":
            (self.candidate_path / "phase-receipt.json").write_bytes(b"changed inside full gate seam")
        return records

    def invoke(self, **changes):
        canonical = workflow.product_reuse._canonical_control
        def observe(path, label):
            value = canonical(path, label)
            if label == "Native validation producer": self.elected_producer = value
            return value
        def checkout(root, producer):
            self.assertEqual(self.root, root)
            self.assertEqual(self.producer, producer)
            if self.failure == "late-checkout" and not self.live:
                raise ValueError("Original checkout changed after input context")
        with patch.object(workflow, "host_classifier", return_value="linux-x64"), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout", side_effect=checkout), \
                patch.object(workflow.product_reuse, "_canonical_control", side_effect=observe), \
                patch.object(workflow.sdk_workflow, "verified_inputs", self.verified), \
                patch.object(workflow.product_reuse, "inspect_products", side_effect=self.inspect), \
                patch.object(workflow.product_reuse, "capture_sdk_native_prepared_upload", side_effect=self.capture) as capture, \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize), \
                patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.package_gate) as package, \
                patch.object(workflow, "_execute_validation", side_effect=self.worker) as worker, \
                patch.object(workflow, "stage_sdk_validation_evidence", side_effect=self.validation_gate) as gate:
            self.capture_mock, self.package_mock, self.worker_mock, self.gate_mock = capture, package, worker, gate
            return workflow.execute(self.plan_path, self.discovery, self.state, self.destination,
                                    **{**self.arguments, **changes})

    def test_original_package_runtime_preparation_and_full_gate_precede_publication(self):
        result = self.invoke()
        self.assertEqual(["enter", "inspect", "capture", "materialize", "package-gate", "worker",
                          "validation-gate", "exit-check", "exited"], self.events)
        self.assertEqual(self.gate_receipt, (self.destination / "shard/phase-receipt.json").read_bytes())
        self.assertEqual("development", result["receipt"]["trustDomain"])
        self.assertEqual(self.producer, result["receipt"]["producer"])
        self.assertEqual("0.3.0", result["receipt"]["productVersion"])
        self.assertEqual(result, verify_phase_shard(self.destination / "shard",
            PhaseInstanceId("sdk", "python", "validation", "linux-x64")))
        self.assertTrue((self.destination / "sdk-validation-evidence/carrier.json").is_file())
        self.assertEqual(b"", (self.destination / "prepared-upload/original/diagnostics/gradle.log").read_bytes())
        self.assertFalse(self.capture_path.exists())
        self.assertEqual(self.package_before, regular_file_inventory(self.package_stage.parent))

    def test_explicit_apple_policy_reaches_current_and_preparation_replays(self):
        policy = fixture.caller_apple_policy(self.root / "caller")
        before = dict(policy)

        def forwarded(delegate):
            def invoke(*args, **kwargs):
                self.assertIs(policy, kwargs.pop("sdk_apple_validation_policy"))
                return delegate(*args, **kwargs)
            return invoke

        with patch.object(self, "verified", side_effect=forwarded(self.verified)) as verified, \
                patch.object(self, "inspect", side_effect=forwarded(self.inspect)) as inspect, \
                patch.object(self, "materialize", side_effect=forwarded(self.materialize)) as materialize:
            result = self.invoke(sdk_apple_validation_policy=policy)
        for replay in (verified, inspect, materialize):
            replay.assert_called_once()
            self.assertIs(policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
        self.assertEqual(before, policy)
        self.assertNotIn("sdkAppleValidationPolicy", result["receipt"])
        self.assertNotIn("sdk_apple_validation_policy", result["receipt"])
        self.assertEqual(["enter", "inspect", "capture", "materialize", "package-gate", "worker",
                          "validation-gate", "exit-check", "exited"], self.events)

    def test_wrong_original_preparation_or_host_prevents_capture(self):
        for failure in ("missing-preparation", "duplicate-preparation", "wrong-key", "wrong-host"):
            with self.subTest(failure=failure):
                self.failure = failure
                changes = {"preparation_build_key": "sha256:" + "e" * 64} if failure == "wrong-key" else {}
                if failure == "wrong-host": changes["target"] = "linux-arm64"
                with self.assertRaises(ValueError): self.invoke(**changes)
                self.capture_mock.assert_not_called()

    def test_selected_contract_runtime_and_preparation_producer_must_match(self):
        for failure in ("unselected", "contract", "runtime", "capture-producer"):
            with self.subTest(failure=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                selection, receipts = deepcopy(self.selection), deepcopy(self.receipt_bytes)
                if failure == "unselected": self.selection["consumers"] = []
                if failure == "contract": self.selection["contractPayloadSha256"] = "sha256:" + "e" * 64
                if failure == "runtime": self.receipt_bytes[next(iter(self.receipt_bytes))] = b"wrong original"
                try:
                    with self.assertRaises(ValueError): self.invoke()
                    self.worker_mock.assert_not_called()
                    self.assertFalse((self.destination / "shard").exists())
                finally:
                    self.selection.clear()
                    self.selection.update(selection)
                    self.receipt_bytes.clear()
                    self.receipt_bytes.update(receipts)

    def test_gate_worker_and_post_context_mutations_never_publish(self):
        for failure in ("package-gate", "package-pairing", "package-plan", "package-producer", "worker",
                        "validation-gate", "validation-candidate", "late-context", "late-checkout",
                        "late-plan", "late-state", "late-policy", "late-input", "late-runtime",
                        "late-capture", "late-stage", "late-candidate", "late-carrier"):
            with self.subTest(failure=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                ready, producer = deepcopy(self.ready), deepcopy(self.producer)
                try:
                    with self.assertRaises(ValueError): self.invoke()
                    if failure.startswith("late-"):
                        self.gate_mock.assert_called_once()
                        self.assertIn("exit-check", self.events)
                    self.assertFalse((self.destination / "shard").exists())
                    self.assertFalse((self.destination / "sdk-validation-evidence").exists())
                finally:
                    self.plan_path.write_bytes(self.original_plan_bytes)
                    self.arguments["keyring"].write_bytes(self.policy_bytes)
                    (self.preparation_state / "control.json").write_bytes(b"original replay control\n")
                    self.ready.clear()
                    self.ready.update(ready)
                    self.producer.clear()
                    self.producer.update(producer)

    def test_retained_carrier_mutation_prevents_final_shard(self):
        publish = workflow.publish_regular_tree
        def changed(source, destination, **kwargs):
            publish(source, destination, **kwargs)
            if destination.name == "prepared-upload":
                (self.destination / "sdk-validation-evidence/carrier.json").write_bytes(b"late mutation")
        with patch.object(workflow, "publish_regular_tree", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "retained evidence changed"): self.invoke()
        self.assertFalse((self.destination / "shard").exists())


class SdkNativeValidationWorkerTest(unittest.TestCase):
    fixture = leaf_fixture.SdkNativePhaseTest.fixture
    predecessor = leaf_fixture.SdkNativePhaseTest.predecessor

    def setUp(self):
        leaf_fixture.SdkNativePhaseTest.setUp(self)
        self.plan.update(phase="validation", target="linux-x64")
        self.plan["buildKey"] = compute_build_key(**{name: self.plan[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        self.stage = self.root / "codex-agent-sdk/build/product-stage/sdk/python/validation"
        package_stage = self.root / "original-package/stage"
        (package_stage / "outputs").mkdir(parents=True)
        (package_stage / "outputs/package").write_bytes(b"original fixture package")
        manifest = write_output_manifest(package_stage, "sdk", "python", "package", "desktop", "0.3.0", {"package": "outputs"})
        path = package_stage.parent / "phase-receipt.json"
        receipt = write_receipt(path, product="sdk", component="python", phase="package", target="desktop",
            version="0.3.0", version_identity="0.3.0", outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.package = {"stage": package_stage, "receiptPath": path, "receipt": receipt}
        self.args = {"producer": self.producer, "sdk_version": "0.3.0", "repository_root": self.root,
            "destination": self.destination, "runtime_stages": self.runtime, "staged_sdks": self.sdks,
            "compatibility_request": self.request, "package": self.package, "predecessor": self.predecessor,
            "environ": {}, "dotnet_executable": None, "dart_executable": None, "dart_package_config": None}
        self.args["protected_inputs"] = []

    def process(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual({"SAFE": "fixed"}, kwargs["env"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        self.assertFalse(kwargs["check"])
        fields = dict(item[2:].split("=", 1) for item in command if item.startswith("-P"))
        self.assertEqual({"codexAgent.product": "sdk", "codexAgent.component": "python",
            "codexAgent.phase": "validation", "codexAgent.target": "linux-x64",
            "codexAgent.candidateCommit": self.producer["commit"], "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.nativeWrapperRuntimeStageRoot": str(self.runtime),
            "codexAgent.nativeWrapperStagedSdkRoot": str(self.sdks),
            "codexAgent.sdkPackageStageRoot": str(self.package["stage"]),
            "codexAgent.sdkPackageReceipt": str(self.package["receiptPath"]),
            "codexAgent.sdkCompatibilityRequest": str(self.request)}, fields)
        self.assertIn("--offline", command)
        self.assertEqual(1, command.count("ciProductPhase"))
        kwargs["stdout"].write(b"raw Gradle\xff\x00\n")
        if self.launch_error: raise OSError("launch failed")
        if self.return_code == 0:
            (self.stage / "outputs/installed").mkdir(parents=True)
            (self.stage / "outputs/installed/raw").write_bytes(b"synthetic raw validation")
            write_output_manifest(self.stage, "sdk", "python", "validation", "linux-x64", "0.3.0",
                                  {"native-wrapper-installed": "outputs/installed"})
        self.after_process()
        return subprocess.CompletedProcess(command, self.return_code)

    def invoke(self, **changes):
        with patch.object(workflow, "host_classifier", return_value=self.host), \
                patch.object(workflow, "_request_inventory", return_value={self.request_input: "original"}), \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout"), \
                patch.object(workflow.product_reuse, "_runtime_worker_environment", return_value=({"SAFE": "fixed"}, self.root / "gradlew")), \
                patch.object(workflow.subprocess, "run", side_effect=self.process):
            return workflow._execute_validation(self.plan, **{**self.args, **changes})

    def test_fixed_imported_only_command_raw_execution_and_no_finalizer(self):
        before = regular_file_inventory(self.package["stage"].parent)
        result = self.invoke()
        self.assertEqual(self.stage, result["stage"])
        self.assertEqual(regular_file_inventory(self.stage), result["outputInventory"])
        self.assertEqual(before, regular_file_inventory(self.package["stage"].parent))
        self.assertEqual(b"raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
        trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(0, trace["returnCode"])
        self.assertEqual(self.calls[0], trace["command"])
        self.assertFalse((self.destination / "shard").exists())

    def test_all_cleanup_roots_reject_existing_originals_before_process(self):
        build, tree = self.root / "codex-agent-sdk/build", self.producer["tree"]
        names = ["product-stage/sdk/python/validation", f"imported-sdk-product-stages/{tree}/python-package",
            f"native-wrapper-capability-inputs/{tree}/python", f"imported-native-wrapper-runtime-stages/{tree}",
            f"native-wrapper-c-abi-sdks/{tree}", f"native-wrapper-package-assets/{tree}"]
        for name in names:
            with self.subTest(name=name):
                path = build / name
                path.mkdir(parents=True)
                sentinel = path / "original"
                sentinel.write_bytes(b"must survive")
                try:
                    with self.assertRaisesRegex(ValueError, "fresh task"):
                        self.invoke(protected_inputs=[sentinel])
                    self.assertEqual(b"must survive", sentinel.read_bytes())
                    self.assertEqual([], self.calls)
                finally:
                    sentinel.unlink()
                    path.rmdir()

    def test_cleanup_descendants_of_outer_policy_are_rejected_before_creation(self):
        policy = self.root / "codex-agent-sdk/build"
        policy.mkdir(parents=True)
        sentinel = policy / "caller-policy.json"
        sentinel.write_bytes(b"original caller policy")
        before = regular_file_inventory(policy)
        with self.assertRaises(ValueError): self.invoke(protected_inputs=[policy])
        self.assertEqual([], self.calls)
        self.assertEqual(before, regular_file_inventory(policy))
        self.assertFalse(self.destination.exists())

    def test_actual_host_and_unrelated_executable_overrides_reject(self):
        self.host = "linux-arm64"
        with self.assertRaisesRegex(ValueError, "actual host"): self.invoke()
        self.host = "linux-x64"
        with self.assertRaisesRegex(ValueError, "selected language"):
            self.invoke(dotnet_executable=self.root / "dotnet")
        self.assertEqual([], self.calls)

    def test_failed_process_retains_raw_failure_trace_without_stage(self):
        self.return_code = 9
        with self.assertRaisesRegex(ValueError, "exit code 9"): self.invoke()
        trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(9, trace["returnCode"])
        self.assertIsNone(trace["launchError"])
        self.assertEqual(b"raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
        self.assertFalse(self.stage.exists())


if __name__ == "__main__":
    unittest.main()

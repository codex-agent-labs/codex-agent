"""Native validation controller controls, not host or signature acceptance.

Election, authenticated inputs/upload, package verification and the final full
carrier gate are explicit seams. Original inventories and shard finalization
are real; the leaf tests execute only a mocked Gradle process.
"""

from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

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
        authorization = self.root / "runtime-authorization"
        authorization.mkdir()
        (authorization / "fixture.sig").write_bytes(b"mocked signature gate only")
        self.arguments["runtime_authorization"] = authorization
        self.tooling = {"evidence": str(tooling), "publicKey": str(public), "javaExecutable": str(java),
                        "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}
        self.policy_bytes = self.arguments["keyring"].read_bytes()

    def inspect(self, *args, **kwargs):
        self.assertEqual(self.tooling, kwargs.pop("sdk_validation_tooling"))
        self.assertEqual(self.arguments["trusted_workflow_sha"], kwargs["sdk_original_workflow_sha"])
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
        component = self.ready["component"]
        self.assertEqual(PhaseInstanceId("sdk", component, "validation", "linux-x64"), identity)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        self.assertEqual(self.tooling, kwargs["sdk_validation_tooling"])
        self.assertEqual(self.arguments["trusted_workflow_sha"], kwargs["sdk_original_workflow_sha"])
        originals = {**self.original_paths, fixture.fixture.CONTRACT: self.contract,
            PhaseInstanceId("sdk", component, "package", "desktop"): {
                "stage": self.package_stage, "receiptPath": self.package_receipt_path}}
        if component == "csharp":
            originals[PhaseInstanceId("sdk", component, "binary", "desktop")] = self.binary
        self.assertEqual(set(originals), set(kwargs.get("materialized_scope", ())))
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
        if self.ready["component"] == "csharp":
            self.assertEqual(regular_file_inventory(self.binary["stage"]),
                             regular_file_inventory(receipt.parent / "csharp-binary/stage"))
            self.assertEqual(self.binary["receiptPath"].read_bytes(),
                             (receipt.parent / "csharp-binary/phase-receipt.json").read_bytes())
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
        self.assertEqual(regular_file_inventory(self.arguments["runtime_authorization"]),
            regular_file_inventory(kwargs["package"]["receiptPath"].parent / "runtime-authorization/linux-x64"))
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
        write_output_manifest(stage, "sdk", self.ready["component"], "validation", "linux-x64", "0.3.0",
                              {"native-wrapper-capability": "outputs/capability"})
        self.result = {"stage": stage, "diagnostics": kwargs["destination"], "outputInventory": regular_file_inventory(stage)}
        return self.result

    def validation_gate(self, records, source, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("validation-gate")
        self.assertFalse((self.destination / "shard").exists())
        self.assertFalse(source.is_relative_to(self.root))
        record, = records
        self.assertEqual((self.ready["component"], "linux-x64"), (record["component"], record["target"]))
        self.assertEqual(regular_file_inventory(self.arguments["runtime_authorization"]),
                         regular_file_inventory(source / record["runtimeAuthorization"]))
        if record["component"] == "csharp":
            self.assertEqual(regular_file_inventory(self.binary["stage"]), regular_file_inventory(source / record["binaryStage"]))
            self.assertEqual(self.binary["receiptPath"].read_bytes(), (source / record["binaryReceipt"]).read_bytes())
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

    def test_prepared_sdk_reference_keeps_inventory_roots_narrow(self):
        from products.sdk_validation import decode_sdk_validation_records
        from products.sdk_validation_inputs import REQUEST_NAME as EVIDENCE_REQUEST
        original_gate = self.validation_gate

        def gate(records, source, destination, **kwargs):
            decoded, = decode_sdk_validation_records(source, records).values()
            self.assertEqual(self.capture_path.parent, source)
            self.assertFalse((source / EVIDENCE_REQUEST).exists())
            self.assertEqual(self.capture_path / "original/staged-sdks", decoded["stagedSdks"])
            self.assertEqual("prepared-upload/original/staged-sdks", records[0]["stagedSdks"])
            self.assertFalse((source / "evidence-source/stagedSdks").exists())
            self.assertEqual(b"opaque original SDK", (decoded["stagedSdks"] / "sdk").read_bytes())
            for name in ("packageStage", "runtimeStages", "validationStage", "runtimeAuthorization",
                         "packageReceipt", "validationReceipt", "compatibilityRequest"):
                self.assertTrue(decoded[name].is_relative_to(source / "evidence-source"))
            return original_gate(records, source, destination, **kwargs)

        for failure in (None, "validation-gate", "late-capture"):
            with self.subTest(failure=failure):
                self.failure = failure
                self.destination = self.root / ("narrow-" + str(failure))
                with patch.object(self, "validation_gate", side_effect=gate), \
                        patch.object(workflow, "snapshot_regular_tree", wraps=snapshot_regular_tree) as snapshots, \
                        patch.object(workflow, "_inventory", wraps=workflow._inventory) as inventories:
                    if failure is None:
                        result = self.invoke()
                        self.assertEqual(self.gate_receipt, (self.destination / "shard/phase-receipt.json").read_bytes())
                        self.assertEqual(b"opaque original SDK", (self.destination / "prepared-upload/original/staged-sdks/sdk").read_bytes())
                        self.assertEqual(self.producer, result["receipt"]["producer"])
                    else:
                        message = "full matcher rejected" if failure == "validation-gate" else "original inputs or preparation capture changed"
                        with self.assertRaisesRegex(ValueError, message):
                            self.invoke()
                        self.assertFalse((self.destination / "shard").exists())
                        self.assertFalse((self.destination / "prepared-upload").exists())
                    captured = self.capture_path
                    self.assertFalse(any(Path(call.args[0]) == captured / "original/staged-sdks"
                                         for call in snapshots.call_args_list))
                    roots = [Path(call.args[0]) for call in inventories.call_args_list]
                    self.assertNotIn(captured.parent, roots)
                    self.assertIn(captured, roots)
                    self.assertIn(captured.parent / "evidence-source", roots)
                    self.gate_mock.assert_called_once()

    def test_current_runtime_reuses_selection_replay_and_rejects_changed_controls(self):
        # Real selection/callback composition; source/semantic gates remain the
        # explicit fixture seams. This is not hosted or Windows acceptance.
        actual_inputs = workflow.sdk_workflow.verified_inputs
        actual_inspect = workflow.product_reuse.inspect_products
        old_inspect, old_capture = self.inspect, self.capture
        self.selection["source"] = "current-runtime"
        identity = PhaseInstanceId("sdk", "python", "validation", "linux-x64")
        context = workflow.product_reuse._VerifiedProductState(
            plan={"validationCommit": self.arguments["policy_revision"]}, producer=self.producer,
            consumer={}, requested=(identity,), closure=(identity,), expected_fixed={},
            rebased_request={}, prior={}, prior_by_instance={}, sources={},
            prior_carrier_phases={}, prior_ready_plans={identity: self.ready})

        def inspect(*args, **kwargs):
            return (actual_inspect(*args, **kwargs) if kwargs.get("include_sdk_selection")
                    else old_inspect(*args, **kwargs))

        @contextmanager
        def verified(*args, **kwargs):
            self.live = True
            try:
                with actual_inputs(*args, **kwargs) as inputs:
                    yield inputs
            finally:
                self.live = False

        def materialize(state, instance, destination, key, root, **kwargs):
            self.assertIs(context, state)
            self.assertEqual(self.root, root)
            return self.materialize(self.plan_path, self.discovery, self.state, instance, destination,
                expected_build_key=key, sdk_validation_tooling=self.tooling,
                sdk_original_workflow_sha=self.arguments["trusted_workflow_sha"], **kwargs)

        def captured_inputs(plan, destination, **kwargs):
            destination.mkdir()

        @contextmanager
        def original_inputs(*args, **kwargs):
            yield {name: self.verified_inputs[name] for name in ("sdk", "runtime")}

        for changed in (False, True):
            with self.subTest(changed=changed):
                self.destination = self.root / ("replayed-" + str(changed))
                def captured_preparation(*args, **kwargs):
                    result = old_capture(*args, **kwargs)
                    if changed:
                        (self.state / "changed-control.json").write_bytes(b"mutation after replay\n")
                    return result
                with patch.object(self, "inspect", side_effect=inspect), \
                        patch.object(self, "verified", side_effect=verified), \
                        patch.object(self, "capture", side_effect=captured_preparation), \
                        patch.object(workflow.product_reuse, "_validate_plan", return_value=context.plan), \
                        patch.object(workflow.product_reuse, "_verified_product_state", return_value=context) as replay, \
                        patch.object(workflow.product_reuse, "_retained_aggregate_handoffs", return_value=[]), \
                        patch.object(workflow.product_reuse, "_sdk_input_selection", return_value=self.selection), \
                        patch.object(workflow.product_reuse, "capture_sdk_inputs_upload", side_effect=captured_inputs), \
                        patch.object(workflow.sdk_workflow, "verified_apple_original_inputs", side_effect=original_inputs), \
                        patch.object(workflow.product_reuse, "_materialize_product_predecessors", side_effect=materialize) as restored:
                    if changed:
                        with self.assertRaisesRegex(ValueError, "original election or caller policy changed"):
                            self.invoke()
                        restored.assert_not_called()
                        self.worker_mock.assert_not_called()
                        self.assertFalse((self.destination / "shard").exists())
                    else:
                        self.invoke()
                        restored.assert_called_once()
                    replay.assert_called_once()

    def test_csharp_worker_and_retained_carrier_receive_unchanged_original_binary(self):
        self.ready["component"] = self.arguments["component"] = "csharp"
        self.ready["buildKey"] = compute_build_key(**{name: self.ready[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        self.arguments["expected_build_key"] = self.ready["buildKey"]
        self.selection["consumers"][0]["component"] = "csharp"
        for phase in ("package", "binary"):
            stage = self.package_stage if phase == "package" else self.root / "original-csharp-binary/stage"
            (stage / "outputs").mkdir(parents=True, exist_ok=True)
            if phase == "binary":
                (stage / "outputs/original.dll").write_bytes(b"synthetic binary predecessor; never executed")
            manifest = write_output_manifest(stage, "sdk", "csharp", phase, "desktop", "0.3.0", {phase: "outputs"})
            receipt_path = stage.parent / "phase-receipt.json"
            receipt = write_receipt(receipt_path, product="sdk", component="csharp", phase=phase,
                target="desktop", version="0.3.0", version_identity="0.3.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": self.producer})
            if phase == "package":
                self.package_receipt = receipt
            else:
                self.binary = {"stage": stage, "receiptPath": receipt_path}
        self.package_before = regular_file_inventory(self.package_stage.parent)
        before = regular_file_inventory(self.binary["stage"].parent)
        self.invoke()
        self.assertEqual(before, regular_file_inventory(self.binary["stage"].parent))

    def test_explicit_apple_policy_reaches_current_and_preparation_replays(self):
        policy = fixture.caller_apple_policy(self.root / "caller")
        before = dict(policy)
        admissions = fixture.caller_metadata_admissions()

        def forwarded(delegate):
            def invoke(*args, **kwargs):
                self.assertIs(policy, kwargs.pop("sdk_apple_validation_policy"))
                for name, admission in admissions.items():
                    self.assertIs(admission, kwargs.pop(name))
                return delegate(*args, **kwargs)
            return invoke

        with patch.object(self, "verified", side_effect=forwarded(self.verified)) as verified, \
                patch.object(self, "inspect", side_effect=forwarded(self.inspect)) as inspect, \
                patch.object(self, "materialize", side_effect=forwarded(self.materialize)) as materialize:
            result = self.invoke(sdk_apple_validation_policy=policy, **admissions)
        for replay in (verified, inspect, materialize):
            replay.assert_called_once()
            self.assertIs(policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
            for name, admission in admissions.items():
                self.assertIs(admission, replay.call_args.kwargs[name])
                self.assertNotIn(name, result["receipt"])
        self.assertEqual(before, policy)
        self.assertNotIn("sdkAppleValidationPolicy", result["receipt"])
        self.assertNotIn("sdk_apple_validation_policy", result["receipt"])
        self.assertEqual(["enter", "inspect", "capture", "materialize", "package-gate", "worker",
                          "validation-gate", "exit-check", "exited"], self.events)

    def test_metadata_policy_cli_preserves_objects_and_context_lifetime(self):
        from ci.tests import test_sdk_native_validation_cli as cli_fixture
        cli = cli_fixture.SdkNativeValidationCliTest(methodName="runTest")
        cli.setUp()
        self.addCleanup(cli.doCleanups)
        fixture.assert_metadata_cli_context(self, workflow, cli.argv)

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
                    diagnostics = self.destination / "failed-validation"
                    self.assertEqual(failure == "validation-gate", diagnostics.exists())
                    if diagnostics.exists():
                        self.assertEqual(self.result["outputInventory"], regular_file_inventory(diagnostics / "stage"))
                        self.assertEqual(self.gate_receipt, (diagnostics / "unadmitted-receipt.json").read_bytes())
                        self.assertFalse(load_canonical_json_bytes((diagnostics / "failure.json").read_bytes())["phaseAdmitted"])
                        self.assertFalse((diagnostics / "phase-receipt.json").exists())
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

    def test_private_windows_scratch_is_empty_scoped_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            with patch.dict(os.environ, {"SystemRoot": str(parent / "Windows")}), \
                    patch.object(workflow.subprocess, "check_output", return_value="runner\\owner\n"), \
                    patch.object(workflow.subprocess, "run") as acl:
                workflow._private_windows_validation_parent(parent)
                acl.assert_called_once_with([str(parent / "Windows/System32/icacls.exe"), str(parent),
                    "/inheritance:r", "/grant:r", "runner\\owner:(OI)(CI)F"], check=True)
                acl.side_effect = subprocess.CalledProcessError(1, "icacls")
                with self.assertRaises(subprocess.CalledProcessError):
                    workflow._private_windows_validation_parent(parent)
                acl.reset_mock()
                original = parent / "original"
                original.write_bytes(b"preserved")
                with self.assertRaisesRegex(ValueError, "must be empty"):
                    workflow._private_windows_validation_parent(parent)
                acl.assert_not_called()
                self.assertEqual(b"preserved", original.read_bytes())

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

    def test_windows_rust_mock_keeps_strict_warnings_with_supported_posix_names(self):
        compiler = self.root / "tool chain/clang.exe"
        compiler.parent.mkdir()
        compiler.write_bytes(b"fixture compiler, not executable evidence")
        with patch.object(workflow.shutil, "which", return_value=str(compiler)):
            self.check_windows_compiler_environment("rust", {
                "CC": "codex-agent-fixture-clang.cmd", "PATH": str(self.destination)})
        launcher = self.destination / "codex-agent-fixture-clang.cmd"
        self.assertEqual((f'@echo off\r\nsetlocal DisableDelayedExpansion\r\n'
                          f'"{compiler}" -D_CRT_NONSTDC_NO_WARNINGS %*\r\n').encode("ascii"),
                         launcher.read_bytes())

    def test_windows_cpp_provisions_keyed_policy_without_changing_the_package(self):
        with patch('sdk_cpp_windows_policy.prepare', return_value=({}, lambda: None)) as prepare:
            self.check_windows_compiler_environment("cpp", {})
        prepare.assert_called_once()
        self.assertEqual((self.root, self.producer['commit'], self.destination), prepare.call_args.args[:3])

    def test_windows_rust_rejects_missing_or_shell_active_compiler_paths(self):
        for index, compiler in enumerate((None, "clang.exe", str(self.root / "bad%clang.exe"),
                                           str(self.root / 'bad"clang.exe'))):
            with self.subTest(compiler=compiler):
                self.destination = self.root / f"build/bad-compiler-{index}"
                self.args["destination"] = self.destination
                with patch.object(workflow.shutil, "which", return_value=compiler), \
                        self.assertRaisesRegex(ValueError, "compiler path is unsafe or missing"):
                    self.check_windows_compiler_environment("rust", {})
                self.assertFalse((self.destination / "codex-agent-fixture-clang.cmd").exists())
                self.assertEqual([], self.calls)

    def check_windows_compiler_environment(self, component, expected):
        self.host = "windows-x64"
        self.plan.update(component=component, target=self.host)
        self.plan["buildKey"] = compute_build_key(**{name: self.plan[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        manifest = write_output_manifest(self.package["stage"], "sdk", component, "package", "desktop", "0.3.0",
                                         {"package": "outputs"})
        self.package["receipt"] = write_receipt(self.package["receiptPath"], product="sdk", component=component,
            phase="package", target="desktop", version="0.3.0", version_identity="0.3.0",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})

        def command(wrapper, fields, environment, **kwargs):
            self.assertEqual({"SAFE": "fixed", **expected}, environment)
            raise RuntimeError("invocation inspected before Gradle")

        with patch.object(workflow.product_reuse, "_runtime_worker_command", side_effect=command), \
                self.assertRaisesRegex(RuntimeError, "invocation inspected"):
            self.invoke()
        self.assertEqual([], self.calls)

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


class RuntimeAuthorizationCaptureTest(unittest.TestCase):
    """Real scoped member hashing; official CI observation is an explicit seam."""

    def test_scoped_capture_retains_original_provenance_and_rejects_tampering(self):
        self._scoped_capture(1)

    def test_imported_capture_uses_exact_new_authority_and_preserves_all_checks(self):
        self._scoped_capture(2)

    def _scoped_capture(self, schema):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            raw = b"unit-only signed-evidence placeholder\n"
            files = [{"relativePath": "fixture.sig", "bytes": len(raw), "sha256": sha256_bytes(raw)}]
            policy = {"schemaVersion": 1, "artifactId": 123, "artifactSha256": "sha256:" + "a" * 64,
                "validationCommit": "b" * 40, "workflowSha": "c" * 40,
                "producer": {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
                    "commit": "d" * 40, "tree": "e" * 40, "event": "workflow_dispatch",
                    "runId": 77, "runAttempt": 2, "pullRequest": None},
                "targets": {target: files for target in NATIVE_TARGETS}}
            if schema == 2:
                policy.update(schemaVersion=2, kind="sdk-runtime-library-imported-validation",
                              workflowSha=policy["validationCommit"])
            archive_path = root / "unit.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("linux-x64/libcodex_agent.so.evidence/fixture.sig", raw)
                archive.writestr("unconsumed-target/not-read", b"not a consumed host input")
            observed = [{"run": {"id": 77, "head_sha": "d" * 40}, "jobs": [{"id": 42}]}]
            artifact = {"id": 123, "digest": policy["artifactSha256"], "expired": False,
                "name": f"codex-agent-runtime-library-authorizations-{policy['validationCommit']}-attestation-77-attempt-2",
                "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/123/zip",
                "workflow_run": {"id": 77, "head_sha": "d" * 40}, "size_in_bytes": archive_path.stat().st_size}
            if schema == 2:
                artifact["name"] = f"runtime-imported-library-authorizations-{policy['validationCommit']}-77-2"
            reads = []
            @contextmanager
            def opened(*args, **kwargs):
                self.assertEqual((artifact, "unit-token"), args)
                self.assertEqual(workflow._LIMIT, kwargs["max_bytes"])
                with ZipFile(archive_path) as archive:
                    real_open = archive.open
                    with patch.object(archive, "open", side_effect=lambda entry, *a, **k:
                            (reads.append(entry.filename), real_open(entry, *a, **k))[1]):
                        yield archive, SimpleNamespace(transferred=len(raw))
            with patch.object(workflow.product_reuse, "_observe_ci_producer_jobs", return_value=observed) as observe, \
                    patch.object(workflow.product_reuse, "api_json", return_value=artifact), \
                    patch.object(workflow.product_reuse, "_contract_ci_upload_metadata",
                        wraps=workflow.product_reuse._contract_ci_upload_metadata) as metadata, \
                    patch.object(workflow.product_reuse, "_require_artifact_job_window") as window, \
                    patch("runtime_reference_archive.open_reference_archive", side_effect=opened):
                output = workflow.capture_runtime_authorization(policy, "linux-x64", root / "capture", token="unit-token")
                self.assertEqual(["linux-x64/libcodex_agent.so.evidence/fixture.sig"], reads)
                self.assertEqual(files, regular_file_inventory(output / "sidecars"))
                transport = load_canonical_json_bytes((output / "transport.json").read_bytes())
                self.assertEqual(policy, transport["source"])
                self.assertEqual(observed, transport["observed"])
                self.assertEqual(len(raw), transport["rangeBytes"])
                self.assertEqual(policy["workflowSha"], observe.call_args.kwargs[
                    "trusted_workflows_by_phase"]["authorization"]["sha"])
                self.assertIsNone(observe.call_args.kwargs["dispatch_authorization_job"])
                self.assertEqual({"authorization": "sdk-runtime-library-validation / " +
                    ("runtime-library-release-authorizations" if schema == 1 else
                     "runtime-library-imported-original-authorizations")},
                    observe.call_args.kwargs["jobs_by_phase"])
                self.assertEqual((123, policy["artifactSha256"]), metadata.call_args.args[:2])
                self.assertEqual(artifact, window.call_args.args[2])
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    workflow.capture_runtime_authorization(policy, "linux-x64", output, token="unit-token")
                bad = deepcopy(policy)
                bad["targets"]["linux-x64"][0]["sha256"] = "sha256:" + "f" * 64
                with self.assertRaisesRegex(ValueError, "immutable digest"):
                    workflow.capture_runtime_authorization(bad, "linux-x64", root / "bad", token="unit-token")
                self.assertFalse((root / "bad").exists())
                reads_before = list(reads)
                artifact["size_in_bytes"] = workflow._LIMIT + 1
                with self.assertRaisesRegex(ValueError, "small evidence bound"):
                    workflow.capture_runtime_authorization(policy, "linux-x64", root / "oversized", token="unit-token")
                self.assertEqual(reads_before, reads)
                self.assertFalse((root / "oversized").exists())
                observe.side_effect = ValueError("original protected job failed")
                with self.assertRaisesRegex(ValueError, "protected job failed"):
                    workflow.capture_runtime_authorization(policy, "linux-x64", root / "failed", token="unit-token")
                self.assertFalse((root / "failed").exists())


if __name__ == "__main__":
    unittest.main()

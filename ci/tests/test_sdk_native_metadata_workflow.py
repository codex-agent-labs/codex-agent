"""Native metadata controller composition; full gates are tested separately."""

from contextlib import contextmanager, redirect_stderr
from copy import deepcopy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_native_metadata_workflow as workflow
from ci.tests import test_sdk_native_package_execution as fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.receipt import compute_build_key, write_output_manifest
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.restore import finalize_phase_object, verify_phase_shard


class SdkNativeMetadataWorkflowTest(unittest.TestCase):
    name = staticmethod(fixture.SdkNativePackageExecutionTest.name)
    fixture = fixture.SdkNativePackageExecutionTest.fixture

    def setUp(self):
        fixture.SdkNativePackageExecutionTest.setUp(self)
        self.destination = self.root / "build/metadata"
        self.preparation = deepcopy(self.ready)
        self.ready = deepcopy(self.ready)
        self.ready["phase"] = "metadata"
        self.ready["buildKey"] = compute_build_key(**{name: self.ready[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        self.instance = PhaseInstanceId("sdk", "python", "metadata", "desktop")
        self.selection["consumers"] = [{"product": "sdk", "component": "python",
                                        "phase": "metadata", "target": "desktop"}]
        for path, contents in {
                self.root / "caller-keyring.json": b"caller product policy\n",
                self.root / "tooling-public.pub": b"caller tooling key\n",
                self.root / "java": b"trusted java fixture\n",
        }.items():
            path.write_bytes(contents)
        (self.root / "caller-keys").mkdir()
        self.tooling_evidence = self.root / "tooling-evidence"
        self.tooling_evidence.mkdir()
        (self.tooling_evidence / "attestation.json").write_bytes(b"caller tooling evidence\n")
        self.tooling = {"evidence": str(self.tooling_evidence),
            "publicKey": str(self.root / "tooling-public.pub"), "javaExecutable": str(self.root / "java"),
            "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}
        self.arguments = {"component": "python", "expected_build_key": self.ready["buildKey"],
            "preparation_component": "python", "preparation_build_key": self.preparation["buildKey"],
            "preparation_state": self.preparation_state, "prepared_artifact_id": 72,
            "prepared_artifact_sha256": "sha256:" + "d" * 64,
            "sdk_inputs_artifact_id": 71, "sdk_inputs_artifact_sha256": "sha256:" + "b" * 64,
            "trusted_workflow_sha": "c" * 40, "keyring": self.root / "caller-keyring.json",
            "keys_directory": self.root / "caller-keys", "repository_root": self.root,
            "environ": {"CONTROL": "explicit environment"}, "token": "synthetic token",
            "tooling_evidence": self.tooling_evidence, "tooling_public_key": self.root / "tooling-public.pub",
            "java_executable": self.root / "java", "required_trust_domain": "development"}
        self.candidate = None

    def tearDown(self):
        fixture.SdkNativePackageExecutionTest.tearDown(self)

    @contextmanager
    def verified(self, *args, **kwargs):
        self.assertEqual((self.plan_path, self.discovery, self.state), args)
        self.assertEqual({"artifact_id": 71, "artifact_sha256": self.arguments["sdk_inputs_artifact_sha256"],
            "trusted_workflow_sha": self.arguments["trusted_workflow_sha"],
            "keyring": self.arguments["keyring"], "keys_directory": self.arguments["keys_directory"],
            "repository_root": self.root, "environ": self.arguments["environ"],
            "token": self.arguments["token"], "sdk_validation_tooling": self.tooling}, kwargs)
        self.events.append("enter")
        self.live = True
        try:
            yield self.verified_inputs
            self.events.append("exit-check")
            if self.failure == "late-context":
                raise ValueError("late SDK authentication failure")
            changed = {
                "late-input": self.destination / "inputs/producer.json",
                "late-runtime": self.destination / f"runtime-stages/{NATIVE_TARGETS[0]}/package/outputs/original",
                "late-staged-sdk": self.destination / "staged-sdks/sdk",
                "late-sdk-input": self.destination / "sdk-inputs/sdk-compatibility-request.json",
                "late-capture": self.capture_path / "original/staged-sdks/sdk",
                "late-candidate": self.candidate / "phase-receipt.json" if self.candidate else self.destination,
            }
            if self.failure in changed:
                changed[self.failure].write_bytes(b"changed after admission\n")
            self.events.append("exited")
        finally:
            self.live = False

    def inspect(self, *args, **kwargs):
        self.assertTrue(self.live)
        self.events.append("inspect")
        self.assertEqual((self.plan_path, self.discovery, self.preparation_state), args)
        self.assertEqual({"repository_root": self.root, "environ": self.arguments["environ"],
                          "sdk_validation_tooling": self.tooling,
                          "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"]}, kwargs)
        rows = [self.preparation]
        if self.failure == "missing-preparation":
            rows = []
        return {"readyPlans": rows}

    def capture(self, plan, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("capture")
        self.capture_path = destination
        self.assertEqual(self.plan_path, plan)
        self.assertEqual(self.preparation, kwargs.pop("expected_phase_plan"))
        self.assertEqual({"artifact_id": 72, "artifact_sha256": self.arguments["prepared_artifact_sha256"],
            "trusted_workflow_sha": self.arguments["trusted_workflow_sha"], "repository_root": self.root,
            "environ": self.arguments["environ"], "token": self.arguments["token"]}, kwargs)
        path = destination / "original/staged-sdks/sdk"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"authenticated staged SDK fixture\n")
        return {"captureProducer": {**self.producer, "runAttempt": 9}
                if self.failure == "wrong-preparation-producer" else self.producer}

    def materialize(self, plan, discovery, state, instance, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("materialize")
        self.assertEqual((self.plan_path, self.discovery, self.state, self.instance, self.destination / "inputs"),
                         (plan, discovery, state, instance, destination))
        self.assertEqual({"expected_build_key": self.ready["buildKey"], "repository_root": self.root,
            "environ": self.arguments["environ"], "sdk_validation_tooling": self.tooling,
            "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"]}, kwargs)
        for identity, original in {**self.original_paths,
                PhaseInstanceId("contract", "contract", "metadata", "common"): self.contract}.items():
            target = destination / self.name(identity)
            snapshot_regular_tree(original["stage"], target / "stage")
            (target / "phase-receipt.json").write_bytes(original["receiptPath"].read_bytes())
        (destination / "producer.json").write_bytes(canonical_json_bytes(self.producer))
        (destination / "phase-plan.json").write_bytes(canonical_json_bytes(self.ready))
        return self.ready

    def metadata(self, plan, discovery, state, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("metadata")
        self.assertEqual((self.plan_path, self.discovery, self.state, self.destination / "candidate"),
                         (plan, discovery, state, destination))
        self.assertEqual({"component": "python", "expected_build_key": self.ready["buildKey"],
            "compatibility_request": self.destination / "sdk-inputs/sdk-compatibility-request.json",
            "runtime_stages": self.destination / "runtime-stages",
            "staged_sdks": self.destination / "staged-sdks", "sdk_validation_tooling": self.tooling,
            "repository_root": self.root, "environ": self.arguments["environ"],
            "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"]}, kwargs)
        self.assertEqual({row["relativePath"] for row in regular_file_inventory(self.sdk)},
                         {row["relativePath"] for row in regular_file_inventory(self.destination / "sdk-inputs")})
        for identity, original in self.original_paths.items():
            self.assertEqual(regular_file_inventory(original["stage"]), regular_file_inventory(
                self.destination / "runtime-stages" / identity.component / identity.phase))
        if self.failure == "metadata":
            raise ValueError("existing five-host metadata caller rejected")
        stage = destination / "stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/metadata.json").write_bytes(b"synthetic admitted metadata output\n")
        write_output_manifest(stage, "sdk", "python", "metadata", "desktop", "0.3.0", {"metadata": "outputs"})
        self.candidate = destination / "worker/shard"
        producer = ({**self.producer, "runAttempt": self.producer["runAttempt"] + 1}
                    if self.failure == "wrong-producer" else self.producer)
        finalized = finalize_phase_object(stage_root=stage, phase_plan=self.ready, producer=producer,
            product_version="0.3.0", trust_domain="development", destination=self.candidate)
        return verify_phase_shard(self.candidate, self.instance) if self.failure != "wrong-result" else {
            **finalized, "receiptBytes": b"wrong"}

    def invoke(self, **changes):
        with patch.object(workflow.sdk_workflow, "verified_inputs", self.verified), \
                patch.object(workflow.product_reuse, "inspect_products", side_effect=self.inspect) as inspect, \
                patch.object(workflow.product_reuse, "capture_sdk_native_prepared_upload",
                             side_effect=self.capture) as capture, \
                patch.object(workflow.product_reuse, "materialize_product_predecessors",
                             side_effect=self.materialize) as materialize, \
                patch.object(workflow.product_reuse, "execute_sdk_metadata", side_effect=self.metadata) as metadata, \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout",
                             side_effect=ValueError("tracked source changed after S858")
                             if self.failure == "late-source" else None) as checkout:
            self.inspect_mock, self.capture_mock = inspect, capture
            self.materialize_mock, self.metadata_mock, self.checkout_mock = materialize, metadata, checkout
            return workflow.execute(self.plan_path, self.discovery, self.state, self.destination,
                                    **{**self.arguments, **changes})

    def test_authenticates_preparation_runtime_and_s858_before_publishing_existing_metadata_shard(self):
        result = self.invoke()
        self.assertEqual(["enter", "inspect", "capture", "materialize", "metadata",
                          "exit-check", "exited"], self.events)
        self.assertEqual(result, verify_phase_shard(self.destination / "shard", self.instance))
        self.assertEqual(b"authenticated staged SDK fixture\n",
                         (self.destination / "prepared-upload/original/staged-sdks/sdk").read_bytes())
        self.assertFalse(self.capture_path.exists())
        self.metadata_mock.assert_called_once()

    def test_same_apple_policy_reaches_all_replays_and_existing_metadata_controller(self):
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
                patch.object(self, "materialize", side_effect=forwarded(self.materialize)) as materialize, \
                patch.object(self, "metadata", side_effect=forwarded(self.metadata)) as metadata:
            result = self.invoke(sdk_apple_validation_policy=policy, **admissions)
        for replay in (verified, inspect, materialize, metadata):
            replay.assert_called_once()
            self.assertIs(policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
            for name, admission in admissions.items():
                self.assertIs(admission, replay.call_args.kwargs[name])
                self.assertNotIn(name, result["receipt"])
        self.assertEqual(before, policy)
        self.assertNotIn("sdkAppleValidationPolicy", result["receipt"])
        self.assertNotIn("sdk_apple_validation_policy", result["receipt"])
        self.assertEqual(["enter", "inspect", "capture", "materialize", "metadata", "exit-check", "exited"], self.events)

    def test_selection_preparation_producer_contract_and_runtime_pairing_fail_before_metadata(self):
        for failure in ("unselected", "missing-preparation", "wrong-preparation-producer", "contract", "runtime"):
            with self.subTest(case=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                selection = deepcopy(self.selection)
                receipts = dict(self.receipt_bytes)
                if failure == "unselected":
                    self.selection["consumers"] = []
                elif failure == "contract":
                    self.selection["contractPayloadSha256"] = "sha256:" + "e" * 64
                elif failure == "runtime":
                    self.receipt_bytes[next(iter(self.receipt_bytes))] = b"wrong original receipt"
                try:
                    with self.assertRaises(ValueError):
                        self.invoke()
                    self.metadata_mock.assert_not_called()
                    self.assertFalse((self.destination / "shard").exists())
                finally:
                    self.selection.clear()
                    self.selection.update(selection)
                    self.receipt_bytes.clear()
                    self.receipt_bytes.update(receipts)

    def test_metadata_and_all_late_input_failures_never_publish_root_shard_or_carrier(self):
        for failure in ("metadata", "wrong-result", "wrong-producer", "late-context", "late-source", "late-input", "late-runtime",
                        "late-staged-sdk", "late-sdk-input", "late-capture", "late-candidate"):
            with self.subTest(case=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                try:
                    with self.assertRaises(ValueError):
                        self.invoke()
                    self.assertFalse((self.destination / "shard").exists())
                    self.assertFalse((self.destination / "prepared-upload").exists())
                finally:
                    self.plan_path.write_bytes(self.original_plan_bytes)

    def test_invalid_identity_overlap_and_tooling_pair_reject_before_context(self):
        for changes in ({"component": "javascript"}, {"preparation_component": "sdk-ios"},
                        {"tooling_keyring": self.root / "tooling-keyring.json"}):
            with self.subTest(changes=changes), patch.object(workflow.sdk_workflow, "verified_inputs") as verified:
                with self.assertRaises(ValueError):
                    self.invoke_without_context(**changes)
                verified.assert_not_called()
        for destination in (self.discovery / "nested", self.tooling_evidence / "nested", self.root.parent / "outside"):
            with self.subTest(destination=destination), patch.object(workflow.sdk_workflow, "verified_inputs") as verified:
                with self.assertRaises(ValueError):
                    self.invoke_without_context(destination=destination)
                verified.assert_not_called()

    def invoke_without_context(self, destination=None, **changes):
        return workflow.execute(self.plan_path, self.discovery, self.state,
            self.destination if destination is None else destination, **{**self.arguments, **changes})


class SdkNativeMetadataCliTest(unittest.TestCase):
    def test_metadata_policy_cli_preserves_objects_and_context_lifetime(self):
        fixture.assert_metadata_cli_context(self, workflow, self.argv)

    def setUp(self):
        self.values = {name: Path("/synthetic") / name for name in
            ("plan", "discovery", "state", "destination", "preparation_state", "keyring", "keys_directory",
             "repository_root", "tooling_evidence", "tooling_public_key", "java_executable")}
        self.values.update(component="python", preparation_component="rust",
            expected_build_key="sha256:" + "a" * 64, preparation_build_key="sha256:" + "b" * 64,
            prepared_artifact_id=72, prepared_artifact_sha256="sha256:" + "c" * 64,
            sdk_inputs_artifact_id=71, sdk_inputs_artifact_sha256="sha256:" + "d" * 64,
            trusted_workflow_sha="e" * 40, required_trust_domain="development")
        names = {"discovery": "discovery-root", "state": "state-root",
                 "preparation_state": "preparation-state"}
        self.argv = [part for name, value in self.values.items()
                     for part in ("--" + names.get(name, name.replace("_", "-")), str(value))]

    def test_cli_forwards_only_fixed_inputs_and_environment_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic token"}, clear=True), \
                patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(self.argv))
            execute.assert_called_once_with(**self.values, tooling_keyring=None, tooling_keys_directory=None,
                                            environ=os.environ, token="synthetic token")

    def test_cli_canonical_apple_policy_forwarding_and_malformed_rejection(self):
        with tempfile.TemporaryDirectory(prefix="native-metadata-apple-cli-") as temporary:
            root = Path(temporary).resolve()
            path = root / "apple policy.json"
            policy = fixture.caller_apple_policy(root)
            raw = canonical_json_bytes(policy)
            path.write_bytes(raw)
            with patch.dict(os.environ, {"GITHUB_TOKEN": "caller token"}, clear=True), \
                    patch.object(workflow, "execute") as execute:
                self.assertEqual(0, workflow.main([*self.argv, "--sdk-apple-validation-policy", str(path)]))
                execute.assert_called_once_with(**self.values, tooling_keyring=None, tooling_keys_directory=None,
                    environ=os.environ, token="caller token", sdk_apple_validation_policy=policy)
                self.assertEqual(raw, path.read_bytes())
            for invalid in (b"{", b"[]\n", b"null\n", b'{ "plan": "noncanonical" }\n'):
                with self.subTest(invalid=invalid), patch.object(workflow, "execute") as execute, \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    path.write_bytes(invalid)
                    workflow.main([*self.argv, "--sdk-apple-validation-policy", str(path)])
                self.assertEqual(2, failure.exception.code)
                execute.assert_not_called()

    def test_cli_rejects_partial_tooling_policy_and_unknown_flags(self):
        for argv in (self.argv + ["--tooling-keyring", "/keyring"], self.argv + ["--command", "anything"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                workflow.main(argv)
            self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()

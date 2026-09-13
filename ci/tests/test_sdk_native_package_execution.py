"""Controller composition controls, not authentication or compiler evidence.

Replay, authenticated input/transport and full package content are explicit mock
boundaries. Original fixture receipts, inventories and private shard creation /
verification remain real. Existing suites test the substituted gates separately.
"""

from contextlib import contextmanager, redirect_stderr
from copy import deepcopy
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_native_package_workflow as workflow
from ci.tests import test_sdk_native_prepare_workflow as fixture
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory
from products.receipt import compute_build_key, write_output_manifest
from products.registry import NATIVE_TARGETS, PhaseInstanceId


class SdkNativePackageExecutionTest(unittest.TestCase):
    materialize = fixture.SdkNativePrepareWorkflowTest.materialize
    tearDown = fixture.SdkNativePrepareWorkflowTest.tearDown
    fixture = fixture.SdkNativePrepareWorkflowTest.fixture

    def setUp(self):
        fixture.SdkNativePrepareWorkflowTest.setUp(self)
        # Current observed transport is CI, while all retained predecessor
        # receipts remain the unchanged synthetic originals from the fixture.
        self.producer = {**self.producer, "workflowPath": ".github/workflows/ci.yml",
            "event": "pull_request", "runId": 71, "runAttempt": 2, "pullRequest": 31}
        self.preparation_state = self.root / "preparation-state"
        self.preparation_state.mkdir()
        (self.preparation_state / "control.json").write_bytes(b"original replay control\n")
        self.preparation = deepcopy(self.ready)
        self.preparation["component"] = "rust"
        self.preparation["buildKey"] = compute_build_key(**{name: self.preparation[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        self.arguments = {
            "component": "python", "expected_build_key": self.ready["buildKey"],
            "preparation_component": "rust", "preparation_build_key": self.preparation["buildKey"],
            "preparation_state": self.preparation_state,
            "prepared_artifact_id": 72, "prepared_artifact_sha256": "sha256:" + "d" * 64,
            "sdk_inputs_artifact_id": 71, "sdk_inputs_artifact_sha256": "sha256:" + "b" * 64,
            "trusted_workflow_sha": "c" * 40, "keyring": self.root / "caller-keyring.json",
            "keys_directory": self.root / "caller-keys", "repository_root": self.root,
            "environ": {"CONTROL": "explicit environment"}, "token": "synthetic token",
        }
        self.capture_path = None
        self.gate_receipt = None

    @staticmethod
    def name(identity):
        return fixture.SdkNativePrepareWorkflowTest.name(identity)

    @contextmanager
    def verified(self, *args, **kwargs):
        self.assertEqual((self.plan_path, self.discovery, self.state), args)
        self.assertEqual({"artifact_id": 71, "artifact_sha256": self.arguments["sdk_inputs_artifact_sha256"],
            **{name: self.arguments[name] for name in ("trusted_workflow_sha", "keyring", "keys_directory",
                                                     "repository_root", "environ", "token")}}, kwargs)
        self.events.append("enter")
        self.live = True
        try:
            yield self.verified_inputs
            self.events.append("exit-check")
            if self.failure == "late-context": raise ValueError("late SDK authentication failure")
            changed = {
                "late-predecessor": self.destination / "inputs/producer.json",
                "late-runtime": self.destination / f"runtime-stages/{NATIVE_TARGETS[0]}/package/outputs/original",
                "late-capture": self.capture_path / "original/prepared-sources/python/source",
                "late-stage": self.result["stage"] / "outputs/package.bin",
                "late-candidate": self.candidate_path / "phase-receipt.json",
                "late-state": self.preparation_state / "control.json",
                "late-plan": self.plan_path,
            }
            if self.failure in changed: changed[self.failure].write_bytes(b"changed after gate\n")
            self.events.append("exited")
        finally:
            self.live = False

    def inspect(self, *args, **kwargs):
        self.assertTrue(self.live)
        self.events.append("inspect")
        self.assertEqual((self.plan_path, self.discovery, self.preparation_state), args)
        self.assertEqual({"repository_root": self.root, "environ": self.arguments["environ"]}, kwargs)
        rows = [self.preparation]
        if self.failure == "missing-preparation": rows = []
        if self.failure == "duplicate-preparation": rows *= 2
        if self.failure == "inspection-mutation":
            (self.preparation_state / "control.json").write_bytes(b"changed by replay seam")
        return {"readyPlans": rows}

    def capture(self, plan, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("capture")
        self.assertEqual(self.plan_path, plan)
        self.assertIs(self.preparation, kwargs["expected_phase_plan"])
        self.assertEqual({"expected_phase_plan": self.preparation,
            "artifact_id": 72, "artifact_sha256": self.arguments["prepared_artifact_sha256"],
            **{name: self.arguments[name] for name in ("trusted_workflow_sha", "repository_root", "environ", "token")}}, kwargs)
        self.assertFalse(destination.is_relative_to(self.root))
        self.capture_path = destination
        for name, raw in {"original/prepared-sources/python/source": b"opaque original wrapper",
                          "original/staged-sdks/sdk": b"opaque original SDK",
                          "original/diagnostics/gradle.log": b"",
                          "original/original-plan/phase-plan.json": canonical_json_bytes(self.preparation)}.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        producer = {**self.producer, "runAttempt": 3} if self.failure == "capture-producer" else self.producer
        return {"captureProducer": producer}

    def worker(self, ready, **kwargs):
        self.assertTrue(self.live)
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual({"producer": self.producer, "sdk_version": "0.3.0", "repository_root": self.root,
            "destination": self.destination / "worker", "runtime_stages": self.destination / "runtime-stages",
            "prepared_sources": self.capture_path / "original/prepared-sources",
            "staged_sdks": self.capture_path / "original/staged-sdks",
            "compatibility_request": self.sdk / fixture.REQUEST_NAME,
            "environ": self.arguments["environ"]}, {name: value for name, value in kwargs.items() if name != "predecessor"})
        for identity, original in self.original_paths.items():
            record = kwargs["predecessor"](identity.product, identity.component, identity.phase, identity.target)
            self.assertEqual(self.receipt_bytes[identity], record["receiptPath"].read_bytes())
            self.assertEqual(regular_file_inventory(original["stage"]),
                regular_file_inventory(kwargs["runtime_stages"] / identity.component / identity.phase))
        if self.failure == "worker": raise ValueError("worker failed")
        stage = self.destination / "synthetic-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/package.bin").write_bytes(b"synthetic unadmitted package")
        write_output_manifest(stage, "sdk", "python", "package", "desktop", "0.3.0", {"package": "outputs"})
        self.result = {"stage": stage, "diagnostics": kwargs["destination"],
            "outputInventory": regular_file_inventory(stage), "stagedSdks": kwargs["staged_sdks"],
            "stagedSdkInventory": regular_file_inventory(kwargs["staged_sdks"])}
        return self.result

    def gate(self, repository, stage, receipt, request, **kwargs):
        self.assertTrue(self.live)
        self.events.append("gate")
        self.assertFalse((self.destination / "shard").exists())
        self.assertEqual((self.root, self.result["stage"], self.sdk / fixture.REQUEST_NAME), (repository, stage, request))
        self.assertFalse(receipt.is_relative_to(self.root))
        self.assertEqual({"runtime_stage_root": self.destination / "runtime-stages",
                          "staged_sdks": self.capture_path / "original/staged-sdks"}, kwargs)
        if self.failure == "gate": raise ValueError("full gate rejected")
        raw = receipt.read_bytes()
        self.candidate_path = receipt.parent
        self.gate_receipt = raw
        return load_canonical_json_bytes(raw), raw + b"different" if self.failure == "gate-pairing" else raw

    def invoke(self, **changes):
        with patch.object(workflow.sdk_workflow, "verified_inputs", self.verified), \
                patch.object(workflow.product_reuse, "inspect_products", side_effect=self.inspect) as inspect, \
                patch.object(workflow.product_reuse, "capture_sdk_native_prepared_upload", side_effect=self.capture) as capture, \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize), \
                patch.object(workflow, "execute_package", side_effect=self.worker) as worker, \
                patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.gate) as gate:
            self.inspect_mock, self.capture_mock, self.worker_mock, self.gate_mock = inspect, capture, worker, gate
            return workflow.execute(self.plan_path, self.discovery, self.state, self.destination,
                                    **{**self.arguments, **changes})

    def test_original_election_upload_runtime_and_private_admission_precede_publication(self):
        result = self.invoke()
        self.assertEqual(["enter", "inspect", "capture", "materialize", "worker", "gate", "exit-check", "exited"], self.events)
        self.assertEqual(self.gate_receipt, (self.destination / "shard/phase-receipt.json").read_bytes())
        self.assertEqual(self.producer, result["receipt"]["producer"])
        self.assertEqual("development", result["receipt"]["trustDomain"])
        self.assertEqual("0.3.0", result["receipt"]["productVersion"])
        self.assertEqual(b"opaque original wrapper",
            (self.destination / "prepared-upload/original/prepared-sources/python/source").read_bytes())
        self.assertFalse(self.capture_path.exists())
        self.assertEqual(self.original_plan_bytes, self.plan_path.read_bytes())

    def test_missing_duplicate_or_wrong_original_preparation_election_denies_capture(self):
        for failure in ("missing-preparation", "duplicate-preparation", "inspection-mutation", "wrong-key"):
            with self.subTest(case=failure):
                self.failure = failure
                try:
                    with self.assertRaises(ValueError):
                        self.invoke(**({"preparation_build_key": "sha256:" + "e" * 64} if failure == "wrong-key" else {}))
                    self.capture_mock.assert_not_called()
                    self.worker_mock.assert_not_called()
                    self.assertFalse((self.destination / "shard").exists())
                finally:
                    (self.preparation_state / "control.json").write_bytes(b"original replay control\n")

    def test_selection_contract_runtime_and_observed_producer_mismatch_prevent_execution(self):
        for failure in ("unselected", "contract", "runtime", "capture-producer"):
            with self.subTest(case=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                selection, receipts = deepcopy(self.selection), deepcopy(self.receipt_bytes)
                if failure == "unselected": self.selection["consumers"] = []
                elif failure == "contract": self.selection["contractPayloadSha256"] = "sha256:" + "e" * 64
                elif failure == "runtime": self.receipt_bytes[next(iter(self.receipt_bytes))] = b"wrong original"
                try:
                    with self.assertRaises(ValueError): self.invoke()
                    self.worker_mock.assert_not_called()
                    self.assertFalse((self.destination / "shard").exists())
                finally:
                    self.selection.clear()
                    self.selection.update(selection)
                    self.receipt_bytes.clear()
                    self.receipt_bytes.update(receipts)

    def test_worker_gate_and_all_late_input_context_failures_never_publish_shard(self):
        for failure in ("worker", "gate", "gate-pairing", "late-context", "late-predecessor", "late-runtime", "late-capture",
                        "late-stage", "late-candidate", "late-state", "late-plan"):
            with self.subTest(case=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                try:
                    with self.assertRaises(ValueError): self.invoke()
                    if failure != "worker":
                        self.gate_mock.assert_called_once()
                    if failure.startswith("late-"):
                        self.assertIn("exit-check", self.events)
                    self.assertFalse((self.destination / "shard").exists())
                    self.assertFalse((self.destination / "prepared-upload").exists())
                finally:
                    self.plan_path.write_bytes(self.original_plan_bytes)
                    (self.preparation_state / "control.json").write_bytes(b"original replay control\n")

    def test_unsupported_component_and_output_overlap_reject_before_replay(self):
        with patch.object(workflow.sdk_workflow, "verified_inputs") as verified:
            for changes in ({"component": "javascript"}, {"preparation_component": "sdk-ios"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    workflow.execute(self.plan_path, self.discovery, self.state, self.destination,
                                     **{**self.arguments, **changes})
            for destination in (self.preparation_state / "nested", self.discovery / "nested",
                                self.root.parent / "outside-output", self.arguments["keys_directory"] / "nested"):
                with self.subTest(destination=destination), self.assertRaises(ValueError):
                    workflow.execute(self.plan_path, self.discovery, self.state, destination, **self.arguments)
                self.assertFalse(destination.exists())
            verified.assert_not_called()


class SdkNativePackageCliTest(unittest.TestCase):
    def setUp(self):
        self.arguments = {name: Path("/synthetic") / name for name in
            ("plan", "discovery", "state", "destination", "preparation_state", "keyring", "keys_directory", "repository_root")}
        self.arguments.update(component="python", preparation_component="rust",
            expected_build_key="sha256:" + "a" * 64, preparation_build_key="sha256:" + "b" * 64,
            prepared_artifact_id=72, prepared_artifact_sha256="sha256:" + "c" * 64,
            sdk_inputs_artifact_id=71, sdk_inputs_artifact_sha256="sha256:" + "d" * 64,
            trusted_workflow_sha="e" * 40)
        names = {"discovery": "discovery-root", "state": "state-root", "preparation_state": "preparation-state-root"}
        self.argv = [part for name, value in self.arguments.items()
                     for part in ("--" + names.get(name, name.replace("_", "-")), str(value))]

    def test_exact_cli_fields_forward_environment_only_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic token"}, clear=True), \
                patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(self.argv))
            execute.assert_called_once_with(**self.arguments, environ=os.environ, token="synthetic token")

    def test_required_identity_and_no_arbitrary_source_or_command_flags(self):
        missing = self.argv.copy()
        index = missing.index("--preparation-state-root")
        del missing[index:index + 2]
        invalid = [missing, ["--prep-state-root" if item == "--preparation-state-root" else item for item in self.argv]]
        for name in ("command", "prepared-sources", "phase-plan", "phase", "token"):
            invalid.append([*self.argv, f"--{name}", "caller override"])
        for flag, value in (("--component", "javascript"), ("--preparation-component", "sdk-ios"),
                            ("--prepared-artifact-id", "not-an-integer")):
            arguments = self.argv.copy()
            arguments[arguments.index(flag) + 1] = value
            invalid.append(arguments)
        for arguments in invalid:
            with self.subTest(argv=arguments), patch.object(workflow, "execute") as execute, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                workflow.main(arguments)
            self.assertEqual(2, failure.exception.code)
            execute.assert_not_called()

    def test_gate_and_io_errors_are_cli_failures(self):
        for error in (ValueError("replay rejected"), OSError("original unavailable")):
            with self.subTest(error=type(error).__name__), patch.object(workflow, "execute", side_effect=error), \
                    redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit) as failure:
                workflow.main(self.argv)
            self.assertEqual(2, failure.exception.code)
            self.assertIn(str(error), output.getvalue())


if __name__ == "__main__":
    unittest.main()

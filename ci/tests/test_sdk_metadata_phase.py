"""Worker composition controls: real shard finalization, simulated execution/admission.

Original host/CI/tooling authority is not established by these synthetic fixtures.
The full metadata admission gate has its own real Git/planner regression suite.
"""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse
import sdk_metadata_phase as worker
from products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import verify_phase_shard
from ci.tests import test_sdk_native_metadata as native_fixture


class SdkMetadataPhaseTest(unittest.TestCase):
    def setUp(self):
        self.support = native_fixture.SdkNativeMetadataTest()
        self.support.setUp()
        self.addCleanup(self.support.doCleanups)
        self.fixture()

    def fixture(self, component="python"):
        self.support.fixture(component)
        self.root = self.support.root
        self.component = component
        original = load_canonical_json_bytes(self.support.args["metadata_receipt"].read_bytes())
        self.plan = {key: original[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        self.producer = self.support.context["producer"]
        self.destination = self.root / "build/worker"
        self.stage = self.root / f"codex-agent-sdk/build/product-stage/sdk/{component}/metadata"
        self.records = {}
        for phase, target in [("package", "desktop"), *(("validation", item) for item in sorted(NATIVE_TARGETS))]:
            path = (self.support.args["package_receipt"] if phase == "package" else
                    self.support.args["validation_receipts"] / f"{target}.json")
            stage = (self.support.args["package_stage"] if phase == "package" else
                     self.support.args["validation_stages"] / target)
            self.records[("sdk", component, phase, target)] = {
                "stage": stage, "receiptPath": path, "receipt": load_canonical_json_bytes(path.read_bytes())}
        self.predecessor_calls = []
        # Deliberately opaque stand-ins at the mocked admission boundary only.
        self.proofs = tuple(object() for _ in sorted(NATIVE_TARGETS))
        self.process_calls, self.admission_calls = [], []
        self.process_exit = 0
        self.after_process = lambda fields: None
        self.after_admission = lambda arguments: None

    def predecessor(self, *identity):
        self.predecessor_calls.append(identity)
        return self.records[identity]

    def capture_sdk(self, request, output):
        self.assertEqual(self.support.args["compatibility_request"], request)
        output.mkdir(parents=True)
        (output / worker.REQUEST_NAME).write_bytes(request.read_bytes())
        (output / "original-empty-diagnostic").write_bytes(b"")

    def process(self, command, **kwargs):
        self.process_calls.append(command)
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn("ciProductPhase", command)
        self.assertIn("--offline", command)
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        self.assertFalse(kwargs["check"])
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual({"codexAgent.product", "codexAgent.component", "codexAgent.phase", "codexAgent.target",
            "codexAgent.candidateCommit", "codexAgent.candidateTree", "codexAgent.sdkPackageStageRoot",
            "codexAgent.sdkPackageReceipt", "codexAgent.sdkCompatibilityRequest", "codexAgent.nativeWrapperRuntimeStageRoot",
            "codexAgent.nativeWrapperStagedSdkRoot", "codexAgent.sdkValidationStagesRoot", "codexAgent.sdkValidationReceiptsRoot"}, set(fields))
        self.assertEqual("sdk", fields["codexAgent.product"])
        self.assertEqual(self.component, fields["codexAgent.component"])
        self.assertEqual("metadata", fields["codexAgent.phase"])
        self.assertEqual("desktop", fields["codexAgent.target"])
        for key in fields:
            if key.endswith(("Root", "Receipt", "Request")):
                self.assertTrue(Path(fields[key]).is_relative_to(self.destination / "inputs"))
        kwargs["stdout"].write(b"original raw Gradle\xff\x00\n")
        if self.process_exit == 0:
            snapshot_regular_tree(self.support.args["metadata_stage"], self.stage)
        self.after_process(fields)
        return subprocess.CompletedProcess(command, self.process_exit)

    def admission(self, **arguments):
        self.admission_calls.append(arguments)
        self.assertIs(self.proofs, arguments["sdk_validation_projections"])
        self.assertEqual(self.root, arguments["repository"])
        self.assertEqual(self.stage, arguments["metadata_stage"])
        self.assertFalse((self.destination / "shard").exists())
        for name in ("package_receipt", "package_stage", "runtime_stages", "staged_sdks"):
            self.assertNotEqual(self.support.args[name], arguments[name])
            if name.endswith("receipt"):
                self.assertEqual(self.support.args[name].read_bytes(), arguments[name].read_bytes())
            else:
                self.assertEqual(regular_file_inventory(self.support.args[name]), regular_file_inventory(arguments[name]))
        for target in sorted(NATIVE_TARGETS):
            self.assertEqual((self.support.args["validation_receipts"] / f"{target}.json").read_bytes(),
                             (arguments["validation_receipts"] / f"{target}.json").read_bytes())
            self.assertEqual(regular_file_inventory(self.support.args["validation_stages"] / target),
                             regular_file_inventory(arguments["validation_stages"] / target))
        original = arguments["metadata_receipt"].read_bytes()
        result = load_canonical_json_bytes(original), original
        self.after_admission(arguments)
        return result

    def invoke(self, **changes):
        arguments = {key: self.support.args[key] for key in (
            "compatibility_request", "runtime_stages", "staged_sdks", "tooling_evidence",
            "tooling_public_key", "java_executable", "policy_revision", "required_trust_domain")}
        arguments.update(repository_root=self.root, destination=self.destination, producer=self.producer,
                         sdk_version="0.2.0", trust_domain="development", predecessor=self.predecessor,
                         sdk_validation_projections=self.proofs, environ={})
        with ExitStack() as stack:
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_environment", return_value=({}, self.root / "gradlew")))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(worker, "_request_inventory", side_effect=lambda _: {
                self.support.request_source: sha256_bytes(self.support.request_source.read_bytes())}))
            stack.enter_context(patch.object(worker, "stage_sdk_inputs", side_effect=self.capture_sdk))
            stack.enter_context(patch.object(worker.subprocess, "run", side_effect=self.process))
            stack.enter_context(patch.object(worker, "verify_sdk_native_metadata_admission", side_effect=self.admission))
            return worker.execute(self.plan, **{**arguments, **changes})

    def test_all_five_languages_use_exact_originals_fixed_task_and_real_candidate_finalizer(self):
        for component in NATIVE_BINDINGS:
            with self.subTest(component=component):
                self.fixture(component)
                before = {name: regular_file_inventory(path) for name, path in self.support.args.items()
                          if name in {"package_stage", "validation_stages", "runtime_stages", "staged_sdks"}}
                result = self.invoke()
                self.assertEqual(result, verify_phase_shard(self.destination / "shard",
                    PhaseInstanceId("sdk", component, "metadata", "desktop")))
                self.assertEqual(self.plan["buildKey"], result["buildKey"])
                self.assertEqual([("sdk", component, "package", "desktop"),
                    *(("sdk", component, "validation", target) for target in sorted(NATIVE_TARGETS))], self.predecessor_calls)
                for name, inventory in before.items():
                    self.assertEqual(inventory, regular_file_inventory(self.support.args[name]))
                self.assertEqual(b"original raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                self.assertEqual(1, len(self.admission_calls))

    def test_nonzero_process_retains_raw_diagnostics_without_admission_or_shard(self):
        self.process_exit = 7
        with self.assertRaisesRegex(ValueError, "exit code 7"):
            self.invoke()
        self.assertEqual(b"original raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
        self.assertEqual(7, load_canonical_json_bytes((self.destination / "execution.json").read_bytes())["returnCode"])
        self.assertEqual([], self.admission_calls)
        self.assertFalse((self.destination / "shard").exists())

    def test_wrong_predecessor_identity_or_inventory_never_executes(self):
        record = self.records[("sdk", "python", "package", "desktop")]
        original = record["receipt"]
        record["receipt"] = {**original, "target": "linux-x64"}
        with self.assertRaisesRegex(ValueError, "elected original receipt"):
            self.invoke()
        record["receipt"] = original
        (record["stage"] / "outputs/original").write_bytes(b"changed original\n")
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual([], self.process_calls)

    def test_original_captured_and_request_reference_changes_fail_before_admission(self):
        for mode in ("original", "captured", "request"):
            with self.subTest(mode=mode):
                self.fixture()
                def change(fields):
                    path = (self.support.args["package_stage"] / "outputs/original" if mode == "original" else
                            Path(fields["codexAgent.sdkPackageStageRoot"]) / "outputs/original" if mode == "captured" else
                            self.support.request_source)
                    path.write_bytes(b"changed after process\n")
                self.after_process = change
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())
                self.assertEqual([], self.admission_calls)

    def test_admission_failure_and_late_stage_or_receipt_mutations_never_publish(self):
        for mode in ("failure", "stage", "receipt"):
            with self.subTest(mode=mode):
                self.fixture()
                def change(arguments):
                    if mode == "failure":
                        raise ValueError("full admission rejected")
                    path = (self.stage / "outputs/evidence/native-metadata.json" if mode == "stage" else
                            arguments["metadata_receipt"])
                    path.write_bytes(path.read_bytes() + b"changed\n")
                self.after_admission = change
                with self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())
                self.assertTrue((self.destination / "gradle.log").is_file())

    def test_fresh_output_and_overlap_checks_preserve_sentinels(self):
        for mode in ("destination", "stage", "overlap", "symlink"):
            with self.subTest(mode=mode):
                self.fixture()
                options = {}
                sentinel = None
                if mode in {"destination", "stage"}:
                    path = self.destination if mode == "destination" else self.stage
                    path.mkdir(parents=True)
                    sentinel = path / "sentinel"
                    sentinel.write_bytes(b"original")
                elif mode == "overlap":
                    options["destination"] = self.support.args["package_stage"] / "worker"
                else:
                    alias = self.root / "linked"
                    alias.symlink_to(self.support.args["package_stage"], target_is_directory=True)
                    options["destination"] = alias / "worker"
                with self.assertRaises(ValueError):
                    self.invoke(**options)
                if sentinel is not None:
                    self.assertEqual(b"original", sentinel.read_bytes())
                self.assertEqual([], self.process_calls)

    def test_unsupported_plan_never_executes(self):
        for change in ({"component": "javascript"}, {"phase": "validation"}, {"target": "linux-x64"}, {"schemaVersion": True}):
            original = self.plan
            self.plan = {**deepcopy(original), **change}
            with self.assertRaises(ValueError):
                self.invoke()
            self.plan = original
        self.assertEqual([], self.process_calls)


if __name__ == "__main__":
    unittest.main()

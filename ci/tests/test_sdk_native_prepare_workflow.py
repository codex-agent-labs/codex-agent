"""Controller lifetime/pairing controls, with election and authentication seams.

Runtime receipts and stage inventories are real deterministic fixture bytes.
Neither the mocked verified context nor preparation leaf proves product/CI trust.
"""

from contextlib import contextmanager, redirect_stderr
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_native_phase as package_fixture
from ci.tests.product_chain_support import write_receipt
import sdk_native_prepare as worker
from products.inventory import regular_file_inventory, snapshot_regular_tree, write_canonical_json
from products.receipt import write_output_manifest
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.sdk_inputs import REQUEST_NAME


CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")


class SdkNativePrepareWorkflowTest(unittest.TestCase):
    fixture = package_fixture.SdkNativePhaseTest.fixture

    def setUp(self):
        package_fixture.SdkNativePhaseTest.setUp(self)
        self.ready = self.plan
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_bytes(b'{"synthetic":"mocked elected input boundary"}\n')
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        contract_stage = self.root / "contract-original/stage"
        (contract_stage / "outputs").mkdir(parents=True)
        (contract_stage / "outputs/contract.zip").write_bytes(b"synthetic current Contract bundle\n")
        manifest = write_output_manifest(contract_stage, "contract", "contract", "metadata", "common",
                                         "0.2.0", {"contract-bundle": "outputs"})
        contract_receipt_path = contract_stage.parent / "phase-receipt.json"
        contract_receipt = write_receipt(contract_receipt_path, product="contract", component="contract",
            phase="metadata", target="common", version="0.2.0", version_identity="0.2.0",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.contract = {"stage": contract_stage, "receiptPath": contract_receipt_path,
                         "receipt": contract_receipt}
        self.original_paths = {PhaseInstanceId(*identity): value for identity, value in self.records.items()}
        self.receipt_bytes = {identity: value["receiptPath"].read_bytes()
                              for identity, value in self.original_paths.items()}
        self.before = regular_file_inventory(self.root / "originals")
        self.contract_before = regular_file_inventory(self.root / "contract-original")
        self.selection = {"source": "released-default", "sdkVersion": "0.3.0",
            "contractPayloadSha256": manifest["outputs"][0]["sha256"],
            "consumers": [{"product": "sdk", "component": language, "phase": "package", "target": "desktop"}
                          for language in NATIVE_BINDINGS]}
        self.sdk = self.root / "verified-sdk"
        self.sdk.mkdir()
        (self.sdk / REQUEST_NAME).write_bytes(b'{"synthetic":"authenticated S858 seam"}\n')
        self.verified_inputs = {"selection": self.selection, "sdk": {"directory": self.sdk},
            "runtime": {"originalPhases": self.original_paths, "receiptBytes": self.receipt_bytes}}
        self.arguments = {"component": "python", "expected_build_key": self.ready["buildKey"],
            "artifact_id": 71, "artifact_sha256": "sha256:" + "b" * 64,
            "trusted_workflow_sha": "c" * 40, "keyring": self.root / "caller-keyring.json",
            "keys_directory": self.root / "caller-keys", "repository_root": self.root,
            "environ": {"CONTROL": "explicit environment"}, "token": "synthetic token"}
        self.events, self.live, self.failure, self.result = [], False, None, None

    def tearDown(self):
        self.assertEqual(self.before, regular_file_inventory(self.root / "originals"))
        self.assertEqual(self.contract_before, regular_file_inventory(self.root / "contract-original"))

    @staticmethod
    def name(identity):
        return "-".join((identity.product, identity.component, identity.phase, identity.target))

    @contextmanager
    def verified(self, *args, **kwargs):
        self.assertEqual((self.plan_path, self.discovery, self.state), args)
        self.assertEqual({key: value for key, value in self.arguments.items()
                          if key not in {"component", "expected_build_key"}}, kwargs)
        self.events.append("enter")
        self.live = True
        try:
            yield self.verified_inputs
            self.events.append("exit-check")
            if self.failure == "late-context":
                raise ValueError("synthetic late original-input rejection")
            if self.failure in {"late-sources", "late-sdks"}:
                key = "preparedSources" if self.failure == "late-sources" else "stagedSdks"
                (self.result[key] / "synthetic").write_bytes(b"changed after worker")
            if self.failure == "late-input":
                (self.destination / "inputs/producer.json").write_bytes(b"changed after worker")
            if self.failure == "late-runtime":
                (self.destination / f"runtime-stages/{NATIVE_TARGETS[0]}/package/outputs/original").write_bytes(b"changed")
            self.events.append("exited")
        finally:
            self.live = False

    def materialize(self, plan, discovery, state, identity, destination, **arguments):
        self.assertTrue(self.live)
        self.events.append("materialize")
        self.assertEqual((self.plan_path, self.discovery, self.state), (plan, discovery, state))
        self.assertEqual(PhaseInstanceId("sdk", "python", "package", "desktop"), identity)
        self.assertEqual(self.destination / "inputs", destination)
        self.assertEqual({"expected_build_key": self.arguments["expected_build_key"],
            "repository_root": self.root, "environ": self.arguments["environ"]}, arguments)
        for original_identity, value in {**self.original_paths, CONTRACT: self.contract}.items():
            directory = destination / self.name(original_identity)
            snapshot_regular_tree(value["stage"], directory / "stage")
            (directory / "phase-receipt.json").write_bytes(value["receiptPath"].read_bytes())
        write_canonical_json(destination / "producer.json", self.producer)
        write_canonical_json(destination / "phase-plan.json", self.ready)
        return self.ready

    def prepare(self, ready, **arguments):
        self.assertTrue(self.live)
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        expected = {"producer": self.producer, "sdk_version": "0.3.0", "repository_root": self.root,
            "destination": self.destination / "worker", "runtime_stages": self.destination / "runtime-stages",
            "compatibility_request": self.sdk / REQUEST_NAME, "environ": self.arguments["environ"]}
        self.assertEqual(expected, {key: value for key, value in arguments.items() if key != "predecessor"})
        expected_files = set()
        for identity, original in self.original_paths.items():
            value = arguments["predecessor"](identity.product, identity.component, identity.phase, identity.target)
            self.assertEqual(self.receipt_bytes[identity], value["receiptPath"].read_bytes())
            self.assertEqual(original["receipt"], value["receipt"])
            self.assertTrue(value["stage"].is_relative_to(self.destination / "inputs"))
            imported = arguments["runtime_stages"] / identity.component / identity.phase
            inventory = regular_file_inventory(original["stage"])
            self.assertEqual(inventory, regular_file_inventory(imported))
            expected_files.update(f"{identity.component}/{identity.phase}/{row['relativePath']}" for row in inventory)
        self.assertEqual(expected_files, {row["relativePath"] for row in regular_file_inventory(arguments["runtime_stages"])})
        if self.failure == "worker":
            raise ValueError("synthetic preparation failure")
        if self.failure == "changed-input":
            (self.destination / "inputs/producer.json").write_bytes(b"changed worker input")
        if self.failure == "changed-runtime":
            (arguments["runtime_stages"] / f"{NATIVE_TARGETS[0]}/package/outputs/original").write_bytes(b"changed")
        sources, sdks = arguments["destination"] / "prepared", arguments["destination"] / "sdks"
        for path in (sources, sdks):
            path.mkdir(parents=True)
            (path / "synthetic").write_bytes(b"unadmitted output fixture")
        self.result = {"preparedSources": sources, "preparedSourcesInventory": regular_file_inventory(sources),
            "stagedSdks": sdks, "stagedSdkInventory": regular_file_inventory(sdks),
            "diagnostics": arguments["destination"]}
        return self.result

    def invoke(self, **changes):
        with patch.object(workflow, "verified_inputs", side_effect=self.verified) as context, \
                patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=self.materialize) as materialize, \
                patch.object(worker, "execute", side_effect=self.prepare) as prepare, \
                patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=AssertionError("preparation cannot finalize")):
            self.context_mock, self.materialize_mock, self.worker_mock = context, materialize, prepare
            return workflow.prepare_native(self.plan_path, self.discovery, self.state, self.destination,
                                           **{**self.arguments, **changes})

    def test_returns_exact_prepared_result_only_after_verified_context_exit(self):
        result = self.invoke()
        self.assertIs(result, self.result)
        self.assertFalse(self.live)
        self.assertEqual(["enter", "materialize", "worker", "exit-check", "exited"], self.events)
        self.assertFalse((self.destination / "shard").exists())

    def test_unselected_or_non_native_component_never_prepares(self):
        self.selection["consumers"] = []
        with self.assertRaisesRegex(ValueError, "selected"):
            self.invoke()
        self.materialize_mock.assert_not_called()
        self.worker_mock.assert_not_called()
        with self.assertRaises(ValueError):
            self.invoke(component="javascript")
        self.context_mock.assert_not_called()

    def test_current_contract_payload_mismatch_rejects_before_preparation(self):
        self.selection["contractPayloadSha256"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "Contract"):
            self.invoke()
        self.worker_mock.assert_not_called()

    def test_runtime_receipt_mismatch_rejects_before_snapshot_and_preparation(self):
        identity = PhaseInstanceId("runtime", NATIVE_TARGETS[0], "package", NATIVE_TARGETS[0])
        self.receipt_bytes[identity] = b"different verified original"
        with self.assertRaisesRegex(ValueError, "predecessor.*verified original"):
            self.invoke()
        self.worker_mock.assert_not_called()
        self.assertFalse((self.destination / f"runtime-stages/{identity.component}/package").exists())

    def test_leaf_failure_does_not_return_or_finalize(self):
        self.failure = "worker"
        with self.assertRaisesRegex(ValueError, "preparation failure"):
            self.invoke()
        self.assertNotIn("exited", self.events)
        self.assertFalse((self.destination / "shard").exists())

    def test_late_context_failure_does_not_return_prepared_outputs(self):
        self.failure = "late-context"
        with self.assertRaisesRegex(ValueError, "late original-input"):
            self.invoke()
        self.assertIsNotNone(self.result)
        self.assertFalse(self.live)
        self.assertNotIn("exited", self.events)

    def test_input_and_output_mutations_do_not_return_success(self):
        for failure in ("changed-input", "changed-runtime", "late-input", "late-runtime", "late-sources", "late-sdks"):
            with self.subTest(failure=failure):
                # Separate controller output trees, same immutable original fixture.
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())

    def test_cli_forwards_fixed_inputs_and_rejects_overrides_abbreviations_and_errors(self):
        paths = {"plan": self.plan_path, "discovery-root": self.discovery, "state-root": self.state,
            "destination": self.destination, "repository-root": self.root,
            "keyring": self.arguments["keyring"], "keys-directory": self.arguments["keys_directory"]}
        argv = ["native-prepare", "--component", "python", *[
            item for name, value in paths.items() for item in (f"--{name}", str(value))]]
        for name in ("expected_build_key", "artifact_id", "artifact_sha256", "trusted_workflow_sha"):
            argv.extend(("--" + name.replace("_", "-"), str(self.arguments[name])))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "cli-token"}, clear=True), \
                patch.object(workflow, "prepare_native") as prepare:
            self.assertEqual(0, workflow.main(argv))
            prepare.assert_called_once_with(self.plan_path, self.discovery, self.state, self.destination,
                **{**self.arguments, "environ": os.environ, "token": "cli-token"})
        invalid = {
            "missing-component": [argv[0], *argv[3:]],
            "unknown-component": [argv[0], "--component", "javascript", *argv[3:]],
            "phase-override": [*argv, "--phase", "validation"],
            "source-override": [*argv, "--prepared-sources", str(self.sources)],
            "command-override": [*argv, "--command", "caller-command"],
            "abbreviated-component": ["--comp" if item == "--component" else item for item in argv],
            "abbreviated-key": ["--expected-build" if item == "--expected-build-key" else item for item in argv],
        }
        for name, values in invalid.items():
            with self.subTest(case=name), patch.object(workflow, "prepare_native") as prepare, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                workflow.main(values)
            self.assertEqual(2, failure.exception.code)
            prepare.assert_not_called()
        for error in (ValueError("original source rejected"), OSError("original input unavailable")):
            stderr = io.StringIO()
            with self.subTest(error=type(error).__name__), \
                    patch.object(workflow, "prepare_native", side_effect=error), \
                    redirect_stderr(stderr), self.assertRaises(SystemExit) as failure:
                workflow.main(argv)
            self.assertEqual(2, failure.exception.code)
            self.assertIn(str(error), stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

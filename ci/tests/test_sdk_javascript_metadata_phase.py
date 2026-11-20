"""Metadata worker controls; simulated Gradle execution is not parity admission."""

from contextlib import ExitStack
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_javascript_phase as phase_fixture
from ci.tests.product_chain_support import write_receipt
import product_reuse
import sdk_javascript_metadata_phase as worker
from products.inventory import load_canonical_json_bytes, regular_file_inventory
from products.receipt import write_output_manifest


class SdkJavaScriptMetadataPhaseTest(unittest.TestCase):
    setUp = phase_fixture.SdkJavaScriptPhaseTest.setUp
    predecessor = phase_fixture.SdkJavaScriptPhaseTest.predecessor

    def fixture(self):
        phase_fixture.SdkJavaScriptPhaseTest.fixture(self, "metadata")
        identity = ("sdk", "javascript", "validation", "node")
        stage = self.root / "originals" / "-".join(identity)
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/original").write_bytes(b"synthetic original validation proof\n")
        manifest = write_output_manifest(stage, *identity, "0.3.0", {"evidence": "outputs"})
        receipt_path = stage.parent / f"{stage.name}.json"
        receipt = write_receipt(receipt_path, product="sdk", component="javascript", phase="validation",
            target="node", outputs=manifest["outputs"], upstream=[], version="0.3.0", version_identity="0.3.0",
            context={"producer": self.producer})
        self.records[identity] = {"stage": stage, "receiptPath": receipt_path, "receipt": receipt}
        self.original_consumer = Path("/authenticated/original/codex-agent-sdk/build/npm/consumer")
        self.output_kind = "binding-evidence"

    def process(self, command, **arguments):
        self.calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "explicit child environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn("--offline", command)
        self.assertEqual(1, command.count("ciProductPhase"))
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual(fields, {
            "codexAgent.product": "sdk", "codexAgent.component": "javascript", "codexAgent.phase": "metadata",
            "codexAgent.target": "node", "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.contractBinaryStage": str(self.records[worker._IDENTITIES[0]]["stage"]),
            "codexAgent.sdkPackageStageRoot": str(self.records[worker._IDENTITIES[1]]["stage"]),
            "codexAgent.sdkValidationStageRoot": str(self.records[worker._IDENTITIES[2]]["stage"]),
            "codexAgent.runtimeBindingValidationStage": str(self.records[worker._IDENTITIES[3]]["stage"]),
            "codexAgent.runtimeBindingValidationVersion": "0.2.3",
            "codexAgent.sdkOriginalConsumerDirectory": str(self.original_consumer),
        })
        arguments["stdout"].write(b"raw metadata\xff\x00\n")
        if self.launch_error:
            raise OSError("synthetic launch failure")
        if self.return_code == 0:
            output = self.stage / "outputs/binding-evidence/javascript-typescript-parity.json"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"synthetic mocked Kotlin output, not proof\n")
            write_output_manifest(self.stage, "sdk", "javascript", "metadata", "node", self.output_version,
                                  {self.output_kind: "outputs/binding-evidence"})
        self.after_process(fields)
        return subprocess.CompletedProcess(command, self.return_code)

    def invoke(self, **changes):
        arguments = dict(producer=self.producer, sdk_version="0.3.0", trust_domain="development",
            repository_root=self.root, destination=self.destination, predecessor=self.predecessor,
            original_consumer_directory=self.original_consumer, environ={})
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value=self.host))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_environment", return_value=(
                {"SAFE": "explicit child environment"}, self.root / "gradlew")))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(worker.subprocess, "run", side_effect=self.process))
            stack.enter_context(patch("products.restore.finalize_phase_object",
                                      side_effect=AssertionError("metadata leaf must not finalize")))
            return worker.execute(self.plan, **{**arguments, **changes})

    def test_fixed_imported_task_returns_only_unadmitted_output_and_preserves_original_versions(self):
        before = regular_file_inventory(self.root / "originals")
        result = self.invoke()
        self.assertEqual(result, {"stage": self.stage, "diagnostics": self.destination,
                                  "outputInventory": regular_file_inventory(self.stage)})
        self.assertEqual(set(worker._IDENTITIES), set(self.predecessor_calls))
        self.assertEqual(before, regular_file_inventory(self.root / "originals"))
        self.assertEqual(b"raw metadata\xff\x00\n", (self.destination / "gradle.log").read_bytes())
        trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(str(self.root), trace["workingDirectory"])
        self.assertEqual(0, trace["returnCode"])
        self.assertFalse((self.destination / "shard").exists())

    def test_failure_and_launch_error_retain_raw_diagnostics(self):
        for launch in (False, True):
            with self.subTest(launch=launch):
                self.fixture()
                self.return_code, self.launch_error = 9, launch
                with self.assertRaises(OSError if launch else ValueError):
                    self.invoke()
                self.assertEqual(b"raw metadata\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(str(self.root), trace["workingDirectory"])
                self.assertEqual(None if launch else 9, trace["returnCode"])
                self.assertFalse(self.stage.exists())

    def test_wrong_route_or_original_directory_rejects_without_execution(self):
        for kind in ("phase", "host", "original"):
            self.fixture()
            if kind == "phase":
                self.plan["phase"] = "package"
            if kind == "host":
                self.host = "macos-arm64"
            arguments = {"original_consumer_directory": Path("relative")} if kind == "original" else {}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.invoke(**arguments)
            self.assertEqual([], self.calls)

    def test_all_four_originals_are_baselined_before_first_manifest_verifier(self):
        real = worker.verify_output_manifest_identity
        last_stage = self.records[worker._IDENTITIES[-1]]["stage"]
        def verify(*arguments, **keywords):
            result = real(*arguments, **keywords)
            (last_stage / "outputs/original").write_bytes(b"changed by first verifier return")
            return result
        with patch.object(worker, "verify_output_manifest_identity", side_effect=verify), \
                self.assertRaisesRegex(ValueError, "original inputs changed"):
            self.invoke()
        self.assertEqual(set(worker._IDENTITIES), set(self.predecessor_calls))
        self.assertEqual([], self.calls)

    def test_fixed_owned_roots_and_aliases_are_never_cleaned(self):
        suffixes = ("product-stage/sdk/javascript/metadata",
                    f"imported-sdk-product-stages/{self.producer['tree']}/javascript-metadata",
                    "javascript-metadata/installed-package", "reports/npm/metadata-sdk-compatibility-archive.json",
                    "reports/javascript-metadata/javascript-typescript-parity.json")
        for suffix in suffixes:
            self.fixture()
            occupied = self.root / "codex-agent-sdk/build" / suffix
            occupied.parent.mkdir(parents=True)
            occupied.write_bytes(b"original sentinel")
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "fresh"):
                self.invoke()
            self.assertEqual(b"original sentinel", occupied.read_bytes())
            self.assertEqual([], self.calls)
        self.fixture()
        alias = self.root / "codex-agent-sdk/build/javascript-metadata/installed-package"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(self.records[worker._IDENTITIES[0]]["stage"], target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.invoke()
        self.assertEqual([], self.calls)

    def test_all_owned_output_ancestors_reject_aliases_before_any_outside_write(self):
        for suffix in ("imported-sdk-product-stages", "javascript-metadata",
                       "reports/npm", "reports/javascript-metadata"):
            self.fixture()
            outside = self.base / f"outside-{self.counter}"
            outside.mkdir()
            (outside / "sentinel").write_bytes(b"original outside bytes")
            before = regular_file_inventory(outside)
            alias = self.root / "codex-agent-sdk/build" / suffix
            alias.parent.mkdir(parents=True)
            alias.symlink_to(outside, target_is_directory=True)
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "unsafe parent"):
                self.invoke()
            self.assertEqual([], self.calls)
            self.assertEqual(before, regular_file_inventory(outside))
            self.assertEqual({"sentinel"}, {path.name for path in outside.iterdir()})
            self.assertFalse(self.destination.exists())

    def test_late_inputs_wrong_output_version_or_kind_cannot_return(self):
        for kind in ("receipt", "plan", "bytecode", "version", "kind"):
            self.fixture()
            if kind == "version":
                self.output_version = "0.3.1"
            elif kind == "kind":
                self.output_kind = "unexpected"
            else:
                def mutate(_fields):
                    if kind == "plan":
                        self.plan["buildKey"] = "sha256:" + "c" * 64
                    else:
                        path = (self.records[worker._IDENTITIES[0]]["receiptPath"] if kind == "receipt"
                                else self.destination / "python-bytecode")
                        path.write_bytes(b"mutated")
                self.after_process = mutate
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.invoke()
            self.assertFalse((self.destination / "shard").exists())


if __name__ == "__main__":
    unittest.main()

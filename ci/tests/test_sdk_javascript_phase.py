"""JS worker controls: simulated execution, real receipt/stage integrity checks.

These fixtures do not establish source, compiler, installed-consumer or CI trust.
Final admission belongs to the caller after its verified-input contexts exit.
"""

from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse
import sdk_javascript_phase as worker
from products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS
from ci.tests.product_chain_support import write_receipt


class SdkJavaScriptPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-javascript-worker-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.counter = 0
        self.fixture()

    def fixture(self, phase="package"):
        self.counter += 1
        self.root = self.base / str(self.counter)
        self.root.mkdir()
        self.destination = self.root / "build/worker"
        self.stage = self.root / f"codex-agent-sdk/build/product-stage/sdk/javascript/{phase}"
        self.producer = {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local",
            "runId": None, "runAttempt": None, "pullRequest": None}
        self.records = {}
        for identity, version in (
            (("contract", "contract", "binary", "common"), "0.2.0"),
            (("runtime", "node-js", "package", "node-js"), "0.2.1"),
            (("runtime", "node-js", "validation", "node-js-binding"), "0.2.3"),
            (("sdk", "javascript", "package", "node"), "0.3.0"),
        ):
            stage = self.root / "originals" / "-".join(identity)
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/original").write_bytes(("synthetic " + "-".join(identity)).encode())
            manifest = write_output_manifest(stage, *identity, version, {"evidence": "outputs"})
            path = stage.parent / f"{stage.name}.json"
            receipt = write_receipt(path, product=identity[0], component=identity[1], phase=identity[2],
                target=identity[3], outputs=manifest["outputs"], upstream=[], version=version,
                version_identity=version, context={"producer": self.producer})
            self.records[identity] = {"stage": stage, "receiptPath": path, "receipt": receipt}
        elected = write_receipt(self.root / "synthetic-elected.json", product="sdk", component="javascript",
            phase=phase, target="node", outputs=manifest["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer})
        self.plan = {name: elected[name] for name in PHASE_PLAN_KEYS}
        self.request = self.root / "authenticated-request.json"
        self.request.write_bytes(b"synthetic caller-verified request boundary\n")
        self.request_input = self.root / "authenticated-original"
        self.request_input.write_bytes(b"original caller-verified K/R bytes\n")
        self.calls, self.predecessor_calls = [], []
        self.return_code = 0
        self.launch_error = False
        self.output_version = "0.3.0"
        self.host = "linux-x64"
        self.after_process = lambda fields: None

    def predecessor(self, *identity):
        self.predecessor_calls.append(identity)
        return self.records[identity]

    def process(self, command, **arguments):
        self.calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "explicit child environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn("ciProductPhase", command)
        self.assertIn("--offline", command)
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual("javascript", fields["codexAgent.component"])
        self.assertEqual(self.plan["phase"], fields["codexAgent.phase"])
        self.assertEqual(self.producer["commit"], fields["codexAgent.candidateCommit"])
        self.assertNotIn("codexAgent.sdkVersion", fields)
        arguments["stdout"].write(b"raw Gradle\xff\x00\n")
        if self.launch_error:
            raise OSError("synthetic process launch failure")
        if self.return_code == 0:
            (self.stage / "outputs").mkdir(parents=True)
            (self.stage / "outputs/synthetic-result").write_bytes(b"not compiler evidence\n")
            write_output_manifest(self.stage, "sdk", "javascript", self.plan["phase"], "node",
                                  self.output_version, {"evidence": "outputs"})
        self.after_process(fields)
        return subprocess.CompletedProcess(command, self.return_code)

    def invoke(self, **changes):
        arguments = dict(producer=self.producer, sdk_version="0.3.0", trust_domain="development",
            repository_root=self.root, destination=self.destination, predecessor=self.predecessor, environ={})
        if self.plan["phase"] == "package":
            arguments["compatibility_request"] = self.request
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value=self.host))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_environment", return_value=(
                {"SAFE": "explicit child environment"}, self.root / "gradlew")))
            self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(worker, "_request_inventory", side_effect=lambda _: {
                self.request_input: sha256_bytes(self.request_input.read_bytes())}))
            stack.enter_context(patch.object(worker.subprocess, "run", side_effect=self.process))
            stack.enter_context(patch("products.restore.finalize_phase_object",
                                      side_effect=AssertionError("premature final admission")))
            return worker.execute(self.plan, **{**arguments, **changes})

    def test_verifier_and_mapper_mutations_reject_before_execution(self):
        for kind in ("stage", "request"):
            with self.subTest(kind=kind):
                self.fixture("package")
                real_verify = worker.verify_output_manifest_identity
                real_properties = worker.properties

                def verify(stage, *arguments, **keywords):
                    result = real_verify(stage, *arguments, **keywords)
                    (Path(stage) / "outputs/original").write_bytes(b"changed after manifest verification")
                    return result

                def properties(*arguments, **keywords):
                    result = real_properties(*arguments, **keywords)
                    self.request.write_bytes(b"changed after property mapping")
                    return result

                name, replacement = (("verify_output_manifest_identity", verify) if kind == "stage"
                                     else ("properties", properties))
                with patch.object(worker, name, side_effect=replacement), self.assertRaisesRegex(ValueError, "changed"):
                    self.invoke()
                self.assertEqual([], self.calls)
                self.assertFalse(self.destination.exists())

    def test_both_phases_return_only_unadmitted_stage_with_original_versions_and_raw_diagnostics(self):
        for phase in ("package", "validation"):
            with self.subTest(phase=phase):
                self.fixture(phase)
                before = regular_file_inventory(self.root / "originals")
                result = self.invoke()
                self.assertEqual({"stage", "diagnostics", "outputInventory"}, set(result))
                self.assertEqual(self.stage, result["stage"])
                self.assertEqual(self.destination, result["diagnostics"])
                self.assertEqual(regular_file_inventory(self.stage), result["outputInventory"])
                self.assertEqual(before, regular_file_inventory(self.root / "originals"))
                self.assertEqual({"gradle.log", "execution.json"}, {path.name for path in self.destination.iterdir()})
                trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(str(self.root), trace["workingDirectory"])
                self.assertEqual(b"raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                self.assertGreaterEqual(self.checkout.call_count, 3)
                fields = dict(value[2:].split("=", 1) for value in self.calls[0] if value.startswith("-P"))
                self.assertEqual(str(self.records[("contract", "contract", "binary", "common")]["stage"]),
                                 fields["codexAgent.contractBinaryStage"])
                if phase == "package":
                    self.assertEqual("0.2.1", fields["codexAgent.runtimePackageVersion"])
                    self.assertEqual(str(self.request), fields["codexAgent.sdkCompatibilityRequest"])
                    self.assertEqual(2, len(self.predecessor_calls))
                else:
                    self.assertEqual("0.2.3", fields["codexAgent.runtimeBindingValidationVersion"])
                    self.assertNotIn("codexAgent.sdkCompatibilityRequest", fields)
                    self.assertEqual(3, len(self.predecessor_calls))

    def test_failure_and_launch_error_keep_exact_bytes_and_execution_diagnostic_without_shard(self):
        for launch in (False, True):
            with self.subTest(launch=launch):
                self.fixture()
                self.return_code, self.launch_error = 7, launch
                with self.assertRaisesRegex(OSError if launch else ValueError, "launch failure" if launch else "exit code 7"):
                    self.invoke()
                self.assertEqual(b"raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(str(self.root), trace["workingDirectory"])
                self.assertEqual(None if launch else 7, trace["returnCode"])
                self.assertFalse((self.destination / "shard").exists())
                self.assertFalse(self.stage.exists())

    def test_original_receipt_stage_request_and_bytecode_mutations_reject(self):
        for kind in ("receipt", "stage", "request", "request-input", "bytecode"):
            with self.subTest(kind=kind):
                self.fixture()
                record = self.records[("contract", "contract", "binary", "common")]
                def mutate(fields):
                    path = {"receipt": record["receiptPath"], "stage": record["stage"] / "outputs/original",
                        "request": self.request, "request-input": self.request_input,
                        "bytecode": self.destination / "python-bytecode"}[kind]
                    path.write_bytes(b"changed input")
                self.after_process = mutate
                with self.assertRaisesRegex(ValueError, "changed|bytecode"):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())

    def test_wrong_original_and_wrong_output_version_reject(self):
        self.records[("contract", "contract", "binary", "common")]["receipt"] = {}
        with self.assertRaisesRegex(ValueError, "original receipt"):
            self.invoke()
        self.assertEqual([], self.calls)
        self.fixture()
        self.output_version = "0.3.1"
        with self.assertRaisesRegex(ValueError, "productVersion"):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())

    def test_wrong_route_host_or_phase_request_never_executes(self):
        for mode in ("route", "host", "missing-request", "validation-request"):
            with self.subTest(mode=mode):
                self.fixture("validation" if mode == "validation-request" else "package")
                arguments = {}
                if mode == "route":
                    self.plan["component"] = "python"
                elif mode == "host":
                    self.host = "macos-arm64"
                else:
                    arguments["compatibility_request"] = self.request if mode == "validation-request" else None
                with self.assertRaises(ValueError):
                    self.invoke(**arguments)
                self.assertEqual([], self.calls)
                self.assertFalse(self.destination.exists())

    def test_occupied_outputs_and_input_overlap_preserve_originals_without_execution(self):
        for mode in ("diagnostics", "stage", "overlap"):
            with self.subTest(mode=mode):
                self.fixture()
                arguments = {}
                if mode == "overlap":
                    original = self.records[("contract", "contract", "binary", "common")]["stage"]
                    arguments["destination"] = original / "worker"
                    sentinel = original / "outputs/original"
                else:
                    directory = self.stage if mode == "stage" else self.destination
                    directory.mkdir(parents=True)
                    sentinel = directory / "sentinel"
                    sentinel.write_bytes(b"preserve me")
                before = sentinel.read_bytes()
                with self.assertRaises(ValueError):
                    self.invoke(**arguments)
                self.assertEqual(before, sentinel.read_bytes())
                self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()

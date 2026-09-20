"""Fixed producer orchestration; mocks confer no compiler or host authority."""

from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_maven_phase as worker
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_file
from products.receipt import write_output_manifest
from ci.tests.product_chain_support import write_receipt


class MavenPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "local", "workflowPath": None, "runId": None, "runAttempt": None, "pullRequest": None}
        self.plan = {"schemaVersion": 1, "product": "sdk", "component": "sdk-core", "phase": "package",
                     "target": "common", "buildKey": "sha256:" + "c" * 64, "inputs": {}}
        self.request = self.root / "originals/compatibility.json"
        self.request.parent.mkdir()
        self.request.write_bytes(b"opaque independently authenticated request\n")
        self.archive = self.root / "originals/runtime.tar.gz"
        self.archive.write_bytes(b"opaque preprovisioned archive; real Gradle checks tracked pins")
        self.destination = self.root / "build/worker"
        self.host = self.enterContext(patch.object(worker, "host_classifier", return_value="linux-x64"))
        self.checkout = self.enterContext(patch.object(worker, "_runtime_worker_checkout"))
        self.environment = self.enterContext(patch.object(worker, "_runtime_worker_environment",
            return_value=({"FIXTURE": "true"}, self.root / "gradlew")))
        self.enterContext(patch.object(worker, "_request_inventory", side_effect=lambda path: {path: sha256_file(path)}))
        self.process = self.enterContext(patch.object(worker.subprocess, "run", side_effect=self.produce))

    def record(self, product, component, phase, target, filename="outputs/data.bin", kind="maven"):
        stage = self.root / "originals" / (component + "-" + phase)
        payload = stage / filename
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(b"original exact stage")
        manifest = write_output_manifest(stage, product, component, phase, target, "0.8.7", {kind: filename})
        receipt_path = stage.parent / (component + "-" + phase + ".json")
        receipt = write_receipt(receipt_path, product=product, component=component, phase=phase, target=target,
            version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.producer})
        return {"stage": stage, "receiptPath": receipt_path, "receipt": receipt}

    def arguments(self, component="sdk-core", phase="package"):
        target = "common" if component == "sdk-core" else "android"
        self.plan.update(component=component, phase=phase, target=target)
        self.host.return_value = "macos-arm64" if (component, phase) == ("sdk-core", "binary") else "linux-x64"
        arguments = dict(producer=self.producer, sdk_version="0.8.7", repository_root=self.root,
                         destination=self.destination, environ={})
        if phase == "package":
            arguments.update(sdk_binary=self.record("sdk", component, "binary", target),
                             compatibility_request=self.request)
        else:
            stem = "codex-agent-contract-0.8.7"
            contract = self.record("contract", "contract", "metadata", "common",
                                   "outputs/" + stem + ".zip", "contract-bundle")
            handoff = self.root / "originals/handoff"
            handoff.mkdir(exist_ok=True)
            (handoff / (stem + ".zip")).write_bytes(b"original exact stage")
            for name in (stem + ".attestation.json", stem + ".attestation.sig", "public-key.pub"):
                (handoff / name).write_bytes(b"opaque caller verified handoff")
            arguments.update(contract_metadata=contract, verified_contract_handoff=handoff)
            if component == "sdk-android":
                arguments["android_runtime_archive"] = self.archive
        return arguments

    def produce(self, command, **kwargs):
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        self.assertFalse(kwargs["check"])
        self.assertEqual(1, command.count("ciProductPhase"))
        self.assertIn("--offline", command)
        base = self.root / ("build" if self.plan["phase"] == "binary" else "codex-agent-sdk/build")
        stage = base / f"product-stage/sdk/{self.plan['component']}/{self.plan['phase']}"
        payload = stage / "outputs/data.bin"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"synthetic output, not compiled")
        write_output_manifest(stage, "sdk", self.plan["component"], self.plan["phase"], self.plan["target"],
                              "0.8.7", {"maven": "outputs/data.bin"})
        return SimpleNamespace(returncode=0)

    def test_all_four_fixed_commands_and_stages(self):
        for component in ("sdk-core", "sdk-android"):
            for phase in ("binary", "package"):
                with self.subTest(component=component, phase=phase):
                    fixture = MavenPhaseTest(methodName="runTest")
                    fixture.setUp()
                    try:
                        args = fixture.arguments(component, phase)
                        result = worker.execute(fixture.plan, **args)
                        command = fixture.process.call_args.args[0]
                        fields = dict(argument[2:].split("=", 1) for argument in command if argument.startswith("-P"))
                        self.assertEqual(component, fields["codexAgent.component"])
                        self.assertEqual(phase, fields["codexAgent.phase"])
                        self.assertEqual({"stage", "diagnostics", "outputInventory"}, set(result))
                        self.assertFalse((fixture.destination / "phase-receipt.json").exists())
                        evidence = load_canonical_json_bytes((fixture.destination / "execution.json").read_bytes())
                        self.assertEqual(command, evidence["command"])
                        self.assertEqual(0, evidence["returnCode"])
                        self.assertEqual(b"", (fixture.destination / "gradle.log").read_bytes())
                        if phase == "package":
                            self.assertIn("codexAgent.sdkCompatibilityRequest", fields)
                            self.assertNotIn("codexAgent.contractPayload", fields)
                        else:
                            self.assertIn("codexAgent.contractPayload", fields)
                            self.assertNotIn("codexAgent.sdkCompatibilityRequest", fields)
                        if (component, phase) == ("sdk-android", "binary"):
                            self.assertEqual(str(fixture.archive), fields["codexAgent.codexArchiveFile"])
                        self.assertTrue(all(name not in fields for name in (
                            "codexAgent.codexVersion", "codexAgent.codexArchiveSha256", "codexAgent.codexBinarySha256")))
                    finally:
                        fixture.doCleanups()

    def test_missing_archive_and_cross_phase_inputs_fail_before_process(self):
        arguments = self.arguments("sdk-android", "binary")
        del arguments["android_runtime_archive"]
        with self.assertRaisesRegex(ValueError, "exact Contract"):
            worker.execute(self.plan, **arguments)
        arguments["android_runtime_archive"] = self.archive
        arguments["compatibility_request"] = self.request
        with self.assertRaises(ValueError):
            worker.execute(self.plan, **arguments)
        self.process.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_wrong_host_existing_output_overlap_and_symbolic_input_fail_early(self):
        arguments = self.arguments()
        self.host.return_value = "macos-arm64"
        with self.assertRaisesRegex(ValueError, "fixed host"):
            worker.execute(self.plan, **arguments)
        self.host.return_value = "linux-x64"
        with self.assertRaisesRegex(ValueError, "overlaps"):
            worker.execute(self.plan, **{**arguments, "destination": arguments["sdk_binary"]["stage"] / "worker"})
        self.destination.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "fresh"):
            worker.execute(self.plan, **arguments)
        link = self.root / "request-link"
        link.symlink_to(self.request)
        with self.assertRaises(ValueError):
            worker.execute(self.plan, **{**arguments, "compatibility_request": link})
        self.process.assert_not_called()

    def test_nonzero_and_launch_error_retain_exact_failure_diagnostics(self):
        arguments = self.arguments()
        self.process.side_effect = None
        self.process.return_value = SimpleNamespace(returncode=17)
        with self.assertRaisesRegex(ValueError, "exit code 17"):
            worker.execute(self.plan, **arguments)
        record = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
        self.assertEqual(17, record["returnCode"])
        self.assertIsNone(record["launchError"])
        self.process.side_effect = OSError("fixture launcher unavailable")
        other = self.root / "build/launch-failure"
        with self.assertRaisesRegex(OSError, "launcher unavailable"):
            worker.execute(self.plan, **{**arguments, "destination": other})
        record = load_canonical_json_bytes((other / "execution.json").read_bytes())
        self.assertIsNone(record["returnCode"])
        self.assertEqual("fixture launcher unavailable", record["launchError"])

    def test_original_input_and_policy_mutation_never_returns_success(self):
        arguments = self.arguments()
        def mutate(command, **kwargs):
            result = self.produce(command, **kwargs)
            self.request.write_bytes(b"changed original request")
            return result
        self.process.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "input changed"):
            worker.execute(self.plan, **arguments)
        self.assertTrue((self.destination / "execution.json").is_file())

    def test_wrong_handoff_or_version_never_launches(self):
        arguments = self.arguments("sdk-core", "binary")
        (arguments["verified_contract_handoff"] / "codex-agent-contract-0.8.7.zip").write_bytes(b"other bundle")
        with self.assertRaisesRegex(ValueError, "handoff differs"):
            worker.execute(self.plan, **arguments)
        self.process.assert_not_called()


if __name__ == "__main__":
    unittest.main()

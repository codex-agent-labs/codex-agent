"""Real retention/receipts/finalization; election, compiler and full gate mocked.

These tests prove orchestration only, not genuine compiler or hosted execution.
"""

from copy import deepcopy
from contextlib import redirect_stderr
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_facade_workflow as workflow
from ci.tests import test_sdk_facade_inputs as fixtures
from ci.tests.product_chain_support import write_receipt
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, snapshot_regular_tree, sha256_file
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, verify_phase_shard
from products.registry import PhaseInstanceId


class FacadeWorkflowTest(unittest.TestCase):
    def test_cli_requires_explicit_context_and_forwards_policy_without_inference(self):
        argv = []
        for name, value in {
            "plan": self.plan, "destination": self.destination, "repository-root": self.root,
            "facade-request": self.f.request, "tooling-evidence": self.tooling,
            "tooling-public-key": self.f.evidence["publicKey"], "java-executable": self.java,
            "discovery-root": self.discovery, "state-root": self.discovery, "target": "jvm",
            "expected-build-key": self.ready["buildKey"], "policy-revision": "a" * 40,
            "android-sdk-directory": "", "required-trust-domain": "development",
        }.items():
            argv.extend(["--" + name, str(value)])
        with patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(argv))
            self.assertEqual("", execute.call_args.kwargs["android_sdk_directory"])
            self.assertEqual(self.f.request, execute.call_args.kwargs["facade_request"])
            self.assertNotIn("sdk_apple_validation_policy", execute.call_args.kwargs)
            archive = self.root / "explicit-native.tar.gz"
            self.assertEqual(0, workflow.main([*argv, "--target", "ios-arm64",
                                             "--native-compiler-archive", str(archive)]))
            self.assertEqual(archive, execute.call_args.kwargs["native_compiler_archive"])
            for invalid in ([*argv, "--tooling-keyring", "unpaired"],
                            [*argv, "--target", "browser"],
                            ["--pl" if arg == "--plan" else arg for arg in argv]):
                execute.reset_mock()
                with self.subTest(argv=invalid), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    workflow.main(invalid)
                execute.assert_not_called()

    def setUp(self):
        self.f = fixtures.FacadeInputsTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.destination = self.root / "worker-upload"
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"{}\n")
        self.discovery = self.root / "discovery"
        self.discovery.mkdir()
        self.producer = {**self.f.producer, "event": "pull_request", "runId": 123, "runAttempt": 1,
                         "pullRequest": 31, "workflowPath": ".github/workflows/ci.yml"}
        self.stage = self.root / "build/product-stage/sdk/sdk-core/validation/jvm"
        content = self.stage / "outputs/validation/facade-validation.json"
        content.parent.mkdir(parents=True)
        content.write_bytes(b'{"fixture":"mocked semantic proof"}\n')
        manifest = write_output_manifest(self.stage, "sdk", "sdk-core", "validation", "jvm", "0.8.7",
                                         {"sdk-facade-validation-content": "outputs/validation"})
        receipt = write_receipt(self.root / "fixture-receipt.json", product="sdk", component="sdk-core",
            phase="validation", target="jvm", version="0.8.7", version_identity="0.8.7",
            outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.ready = {key: receipt[key] for key in PHASE_PLAN_KEYS}
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        (self.tooling / "fixture.jar").write_bytes(b"mocked signed tooling")
        self.java = self.root / "java"
        self.java.write_bytes(b"mocked Java")
        self.full_calls = []
        self.enterContext(patch.object(workflow, "_request_inventory", side_effect=lambda path: {path: sha256_file(path)}))
        self.enterContext(patch.object(workflow, "stage_sdk_inputs", side_effect=self.f.stage_inputs))
        self.materialize = self.enterContext(patch.object(workflow.product_reuse, "materialize_product_predecessors",
                                                        side_effect=self.materialize_inputs))
        self.worker = self.enterContext(patch.object(workflow, "execute_validation", side_effect=self.execute_worker))
        self.full = self.enterContext(patch.object(workflow, "verify_sdk_facade_validation_original_content", side_effect=self.replay))
        self.checkout = self.enterContext(patch.object(workflow.product_reuse, "_runtime_worker_checkout"))
        self.finalize = self.enterContext(patch.object(workflow.product_reuse, "finalize_phase_object",
                                                     wraps=workflow.product_reuse.finalize_phase_object))

    def materialize_inputs(self, plan, discovery, state, instance, output, **kwargs):
        self.assertEqual(PhaseInstanceId("sdk", "sdk-core", "validation", "jvm"), instance)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        output.mkdir()
        for name, stage, receipt in (("sdk-sdk-core-package-common", self.f.f.package, self.f.receipt),
                ("contract-contract-metadata-common", self.f.f.contract, Path(self.f.evidence["phaseReceipt"]))):
            snapshot_regular_tree(stage, output / name / "stage")
            (output / name / "phase-receipt.json").write_bytes(receipt.read_bytes())
        (output / "phase-plan.json").write_bytes(canonical_json_bytes(self.ready))
        (output / "producer.json").write_bytes(canonical_json_bytes(self.producer))
        return deepcopy(self.ready)

    def execute_worker(self, ready, *, producer, repository_root, destination, facade_request, environ):
        self.assertEqual(self.ready, ready)
        self.assertEqual(self.producer, producer)
        self.assertFalse((self.destination / "shard").exists())
        value, _ = workflow._request(facade_request)
        self.assertEqual(self.f.receipt.read_bytes(), Path(value["packageReceipt"]).read_bytes())
        self.assertNotEqual(self.f.value["packageReceipt"], value["packageReceipt"])
        destination.mkdir()
        (destination / "facade-request.json").write_bytes(facade_request.read_bytes())
        (destination / "execution.json").write_bytes(b"{}\n")
        (destination / "gradle.log").write_bytes(b"")
        (destination / "source").mkdir()
        (destination / "source/template").write_bytes(b"mocked immutable source")
        work = self.root / "build/imported-sdk-facade-validation" / producer["tree"] / "jvm"
        for name in ("inputs", "execution", "consumer-inputs", "consumer"):
            (work / name).mkdir(parents=True)
            (work / name / "fixture.json").write_bytes(b"{}\n")
        for name in ("publication-metadata.json", "report.json", "compiler-inputs.json"):
            (work / name).write_bytes(b"{}\n")
        return {"stage": self.stage, "outputInventory": workflow._inventory(self.stage), "work": work,
                "inputs": work / "inputs", "execution": work / "execution", "consumerInputs": work / "consumer-inputs"}

    def replay(self, **kwargs):
        self.assertFalse((self.destination / "shard").exists())
        self.assertEqual({"repositoryRoot": str(self.root), "androidSdkDirectory": ""}, kwargs["original_context"])
        self.assertEqual(self.tooling, kwargs["tooling_evidence"])
        self.full_calls.append(kwargs)
        raw = kwargs["validation_receipt"].read_bytes()
        return load_canonical_json_bytes(raw), raw

    def call(self, **changes):
        arguments = dict(target="jvm", expected_build_key=self.ready["buildKey"], facade_request=self.f.request,
            android_sdk_directory="", tooling_evidence=self.tooling,
            tooling_public_key=Path(self.f.evidence["publicKey"]), java_executable=self.java,
            policy_revision="a" * 40, required_trust_domain="development", repository_root=self.root, environ={})
        arguments.update(changes)
        return workflow.execute(self.plan, self.discovery, None, self.destination, **arguments)

    def test_retains_original_bytes_and_finalizes_only_after_full_replay(self):
        original_request = self.f.request.read_bytes()
        result = self.call()
        self.assertEqual(1, len(self.full_calls))
        self.finalize.assert_called_once()
        verified = verify_phase_shard(self.destination / "shard", PhaseInstanceId("sdk", "sdk-core", "validation", "jvm"))
        self.assertEqual(self.producer, verified["receipt"]["producer"])
        self.assertEqual("development", verified["receipt"]["trustDomain"])
        self.assertEqual(verified["receiptBytes"], result["shard"]["receiptBytes"])
        self.assertEqual(original_request, (self.destination / "originals/original-request.json").read_bytes())
        self.assertEqual(original_request, self.f.request.read_bytes())
        self.assertEqual({"inputs", "originals", "worker", "selection", "context", "retained-execution", "shard"},
                         {path.name for path in self.destination.iterdir()})

    def test_archive_role_guard_precedes_election_and_does_not_infer_cache(self):
        archive = self.root / "caller.tar.gz"
        archive.write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError, "Nonnative"):
            self.call(native_compiler_archive=archive)
        with self.assertRaisesRegex(ValueError, "requires an independent"):
            self.call(target="ios-arm64")
        self.materialize.assert_not_called()
        self.finalize.assert_not_called()

    def test_unsupported_native_policy_rejects_before_materialization_or_producer(self):
        archive = self.root / "independent-native.tar.gz"
        archive.write_bytes(b"caller archive cannot establish unsupported host policy")
        for target in ("macos-x64", "linux-arm64", "linux-x64", "windows-x64"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "no supported pinned"):
                self.call(target=target, native_compiler_archive=archive)
        self.materialize.assert_not_called()
        self.finalize.assert_not_called()
        self.full.assert_not_called()
        self.worker.assert_not_called()

    def test_external_archive_forwarding_and_late_mutation_never_finalize(self):
        archive = self.root / "caller-native.tar.gz"
        with archive.open("wb") as stream:
            stream.truncate(17 * 1024 * 1024)
        def mutate(**kwargs):
            self.assertEqual(archive, kwargs["native_compiler_archive"])
            result = self.replay(**kwargs)
            archive.write_bytes(b"changed after replay")
            return result
        self.full.side_effect = mutate
        # Only the target-role boundary is mocked to reuse the real JVM stage
        # fixture. This checks controller forwarding/lifetime, not native policy.
        with patch.object(workflow, "_native_archive_path", return_value=archive), \
                patch.object(workflow, "_PINNED_NATIVE_TARGETS", {"jvm"}), \
                self.assertRaisesRegex(ValueError, "changed"):
            self.call(native_compiler_archive=archive)
        self.finalize.assert_not_called()

    def test_election_failure_cannot_run_worker_or_finalize(self):
        self.materialize.side_effect = ValueError("not elected")
        with self.assertRaisesRegex(ValueError, "not elected"):
            self.call()
        self.worker.assert_not_called()
        self.finalize.assert_not_called()

    def test_retains_only_named_public_keys_not_private_or_unrelated_files(self):
        keys = self.root / "policy-keys"
        keys.mkdir()
        for name in ("active.pub", "retired.pub", "private.key", "unrelated.pub"):
            (keys / name).write_bytes(name.encode())
        keyring = self.root / "keyring.json"
        keyring.write_bytes(b"{}\n")
        for label in ("binaryContractEvidence", "validationContractEvidence"):
            self.f.value[label].update(keyring=str(keyring), keysDirectory=str(keys))
        self.f.request.write_bytes(canonical_json_bytes(self.f.value))
        with patch.object(workflow, "load_keyring", return_value={
                "activeKey": {"keyId": "active"}, "retiredKeys": [{"keyId": "retired"}]}):
            self.call()
        for label in ("binaryContractEvidence", "validationContractEvidence"):
            retained = self.destination / "originals/trees" / label / "keysDirectory"
            self.assertEqual({"active.pub", "retired.pub"}, {path.name for path in retained.iterdir()})
            for key in retained.iterdir():
                self.assertEqual((keys / key.name).read_bytes(), key.read_bytes())
        self.assertEqual(b"private.key", (keys / "private.key").read_bytes())

    def test_different_selected_predecessor_cannot_run_worker(self):
        def different(*args, **kwargs):
            ready = self.materialize_inputs(*args, **kwargs)
            (args[4] / "sdk-sdk-core-package-common/phase-receipt.json").write_bytes(b"{}\n")
            return ready
        self.materialize.side_effect = different
        with self.assertRaisesRegex(ValueError, "elected original predecessor"):
            self.call()
        self.worker.assert_not_called()
        self.finalize.assert_not_called()

    def test_full_gate_failure_cannot_finalize(self):
        self.full.side_effect = ValueError("full replay failed")
        with self.assertRaisesRegex(ValueError, "full replay failed"):
            self.call()
        self.finalize.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_late_input_mutation_cannot_finalize(self):
        def mutate(**kwargs):
            result = self.replay(**kwargs)
            self.java.write_bytes(b"changed after gate")
            return result
        self.full.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "inputs or retained evidence changed"):
            self.call()
        self.finalize.assert_not_called()

    def test_retained_evidence_mutation_cannot_finalize(self):
        def mutate(**kwargs):
            result = self.replay(**kwargs)
            (self.destination / "retained-execution/report.json").write_bytes(b"changed")
            return result
        self.full.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "inputs or retained evidence changed"):
            self.call()
        self.finalize.assert_not_called()

    def test_wrong_replay_receipt_cannot_finalize(self):
        self.full.side_effect = lambda **kwargs: ({}, b"{}\n")
        with self.assertRaisesRegex(ValueError, "different original receipt"):
            self.call()
        self.finalize.assert_not_called()

    def test_invalid_context_and_existing_output_reject(self):
        with self.assertRaisesRegex(ValueError, "Android SDK context"):
            self.call(android_sdk_directory="invalid\ncontext")
        self.worker.assert_not_called()
        with self.assertRaisesRegex(ValueError, "fresh and normalized"):
            self.call()
        self.finalize.assert_not_called()


if __name__ == "__main__":
    unittest.main()

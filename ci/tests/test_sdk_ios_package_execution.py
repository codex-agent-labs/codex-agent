"""Controller-order tests; authority, tooling, and host execution are mocked."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_ios_package_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from products.inventory import canonical_json_bytes, regular_file_inventory, write_canonical_json
from products.receipt import write_output_manifest


class SdkIosPackageExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-package-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.discovery.mkdir(); self.state.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b'{"synthetic":"verified plan boundary"}\n')
        self.plan_bytes = self.plan.read_bytes()
        self.destination = self.root / "build/package"
        self.developer = self.root / "Applications/Xcode.app/Contents/Developer"
        self.developer.mkdir(parents=True)
        self.producer = {
            "repository": "owner/repository",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "event": "pull_request",
            "runId": 7,
            "runAttempt": 2,
            "pullRequest": 3,
        }
        self.ready = {
            "schemaVersion": 1,
            "product": "sdk",
            "component": "sdk-ios",
            "phase": "package",
            "target": "ios",
            "buildKey": "sha256:" + "c" * 64,
            "inputs": {},
        }
        self.expected_key = self.ready["buildKey"]
        self.sdk_directory = self.root / "verified-sdk"
        self.sdk_directory.mkdir()
        (self.sdk_directory / "sdk-compatibility-request.json").write_bytes(b"request\n")
        self.arguments = {}
        for name in (
            "contract_payload",
            "contract_metadata_receipt",
            "contract_attestation",
            "contract_attestation_signature",
            "contract_public_key",
        ):
            path = self.sdk_directory / name
            path.write_bytes(f"synthetic {name}\n".encode())
            self.arguments[name] = path
        self.arguments.update({
            "required_trust_domain": "release",
            "contract_keyring": self.root / "keyring.json",
            "contract_keys_directory": self.root / "keys",
        })
        self.arguments["contract_keyring"].write_bytes(b"policy\n")
        self.arguments["contract_keys_directory"].mkdir()
        self.sdk_inputs = {
            "selection": {
                "consumers": [{
                    "product": "sdk", "component": "sdk-ios", "phase": "package", "target": "ios",
                }],
                "sdkVersion": "0.8.0",
            },
            "sdk": {"directory": self.sdk_directory, "arguments": self.arguments},
        }
        self.tooling = self.root / "tooling"
        self.tooling.mkdir(); (self.tooling / "receipt.json").write_bytes(b"tooling\n")
        self.tooling_key = self.root / "tooling.pub"; self.tooling_key.write_bytes(b"public\n")
        self.java = self.root / "java"; self.java.write_bytes(b"java\n")
        self.events = []
        self.admissions = {}
        self.context_failure = None
        self.gate_failure = False
        self.contract_mismatch = False
        self.finalized = None

    @contextmanager
    def verified_inputs(self, *args, **kwargs):
        self.assertEqual(self.tooling_policy, kwargs["sdk_validation_tooling"])
        self.assert_apple_policy(kwargs)
        self.assert_admissions(kwargs)
        self.events.append("sdk-enter")
        try:
            yield self.sdk_inputs
            self.events.append("sdk-exit")
            if self.context_failure == "sdk":
                (self.result["stage"] / "changed-after-gate").write_bytes(b"changed\n")
            elif self.context_failure == "sdk-prepared":
                (self.destination / "inputs/changed-after-gate").write_bytes(b"changed\n")
            elif self.context_failure == "capture":
                (self.destination / "package-execution/input-binding.json").write_bytes(b"changed\n")
            elif self.context_failure == "capture-context":
                (self.destination / "apple-package-execution.json").write_bytes(b"changed\n")
            elif self.context_failure == "source-plan":
                self.plan.write_bytes(b"changed source plan after package gate\n")
            elif self.context_failure == "retained-plan":
                (self.destination / "original-plan/impact-plan.json").write_bytes(
                    b"changed retained plan after package gate\n"
                )
        finally:
            self.events.append("sdk-closed")

    def materialize(self, *args, **kwargs):
        self.assertEqual(self.tooling_policy, kwargs["sdk_validation_tooling"])
        self.assert_apple_policy(kwargs)
        self.assert_admissions(kwargs)
        self.events.append("materialize")
        prepared = args[4]
        prepared.mkdir(parents=True)
        write_canonical_json(prepared / "producer.json", self.producer)
        records = (
            ("contract", "contract", "binary", "common", "0.2.0"),
            ("contract", "contract", "metadata", "common", "0.2.0"),
            ("sdk", "sdk-ios", "binary", "ios", "0.8.0"),
        )
        for product, component, phase, target, version in records:
            directory = prepared / "-".join((product, component, phase, target))
            output = directory / "stage/outputs/artifact.bin"
            output.parent.mkdir(parents=True)
            output.write_bytes(f"{product}/{component}/{phase}/{target}\n".encode())
            manifest = write_output_manifest(
                directory / "stage", product, component, phase, target, version,
                {"contract-bundle" if phase == "metadata" else "fixture": "outputs"},
            )
            receipt = directory / "phase-receipt.json"
            write_receipt(
                receipt,
                product=product,
                component=component,
                phase=phase,
                target=target,
                version=version,
                version_identity=version,
                outputs=manifest["outputs"],
                upstream=[],
                context={"producer": self.producer},
            )
            if phase == "metadata":
                self.arguments["contract_metadata_receipt"].write_bytes(receipt.read_bytes())
        if self.contract_mismatch:
            self.arguments["contract_metadata_receipt"].write_bytes(b"different Contract receipt\n")
        return self.ready

    def assert_admissions(self, options):
        actual = {name: options[name] for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission") if name in options}
        self.assertEqual(set(self.admissions), set(actual))
        for name, value in self.admissions.items():
            self.assertIs(value, actual[name])

    def assert_apple_policy(self, arguments):
        if self.apple_policy is None:
            self.assertNotIn("sdk_apple_validation_policy", arguments)
        else:
            self.assertIs(self.apple_policy, arguments["sdk_apple_validation_policy"])

    def worker(self, ready, **arguments):
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual(self.producer, arguments["producer"])
        self.assertNotIn("sdk_apple_validation_policy", arguments)
        self.assertEqual(
            {"SAFE": "environment", "DEVELOPER_DIR": str(self.developer)},
            arguments["environ"],
        )
        self.assertEqual(
            self.sdk_directory / "sdk-compatibility-request.json",
            arguments["compatibility_request"],
        )
        self.assertTrue({
            "verified_distribution",
            "native_evidence",
            "expected_sdk_compatibility",
            "expected_distribution_proof",
        }.isdisjoint(arguments))
        stage = self.destination / "synthetic-stage"
        stage.mkdir()
        (stage / "output").write_bytes(b"synthetic package output\n")
        self.result = {
            "stage": stage,
            "diagnostics": self.destination / "worker",
            "outputInventory": regular_file_inventory(stage),
        }
        return self.result

    def finalize(self, **arguments):
        self.events.append("finalize")
        candidate = arguments["destination"]
        candidate.mkdir()
        receipt = {"synthetic": "candidate receipt"}
        (candidate / "phase-receipt.json").write_bytes(canonical_json_bytes(receipt))
        (candidate / "phase-object.json").write_bytes(b"synthetic object\n")
        self.finalized = {"receipt": receipt, "synthetic": "verified shard"}
        return self.finalized

    def gate(self, repository, stage, receipt, request, **arguments):
        self.events.append("gate")
        if self.gate_failure:
            raise ValueError("synthetic full package rejection")
        self.assertIn("sdk-enter", self.events)
        self.assertNotIn("sdk-exit", self.events)
        self.assertEqual(self.result["stage"], stage)
        self.assertNotIn("sdk_apple_validation_policy", arguments)
        self.assertEqual(self.sdk_directory / "sdk-compatibility-request.json", request)
        self.assertEqual(self.destination / "inputs/sdk-sdk-ios-binary-ios/stage",
                         arguments["binary_stage_root"])
        apple = arguments["apple_binary_verification"]
        self.assertEqual({
            "developer_directory": self.developer,
            "repository": self.root,
            "tooling_evidence": self.tooling,
            "tooling_public_key": self.tooling_key,
            "java_executable": self.java,
            "policy_revision": "9" * 40,
            "required_trust_domain": "development",
            "tooling_keyring": None,
            "tooling_keys_directory": None,
        }, apple)
        capture = arguments["apple_execution_capture_directory"]
        self.assertEqual(self.destination / "package-execution", capture)
        (capture / "events").mkdir(parents=True)
        (capture / "events/combined.bin").write_bytes(b"")
        (capture / "input-binding.json").write_bytes(b"mock captured binding\n")
        raw = receipt.read_bytes()
        return self.finalized["receipt"], raw

    def execution_context(self, **arguments):
        self.events.append("capture-context")
        self.assertIn("gate", self.events)
        self.assertNotIn("sdk-exit", self.events)
        self.assertEqual(self.producer, arguments["producer"])
        self.assertEqual(11, arguments["sdk_inputs_artifact_id"])
        self.assertEqual("sha256:" + "1" * 64, arguments["sdk_inputs_artifact_sha256"])
        self.assertEqual(self.destination / "inputs/sdk-sdk-ios-binary-ios/phase-receipt.json",
                         arguments["binary_receipt"])
        self.assertEqual(self.result["stage"] / "outputs/evidence/sdk-compatibility.json",
                         arguments["sdk_compatibility"])
        return {"synthetic": "external capture binding, not authority",
                "captureFiles": regular_file_inventory(arguments["capture_directory"], allow_empty=True)}

    def invoke(self, **changes):
        self.tooling_policy = {
            "evidence": str(self.tooling),
            "publicKey": str(self.tooling_key),
            "javaExecutable": str(self.java),
            "requiredTrustDomain": "development",
            "keyring": None,
            "keysDirectory": None,
        }
        self.apple_policy = changes.get("sdk_apple_validation_policy")
        self.admissions = {name: changes[name] for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission") if name in changes}
        arguments = dict(
            expected_build_key=self.expected_key,
            sdk_inputs_artifact_id=11,
            sdk_inputs_artifact_sha256="sha256:" + "1" * 64,
            trusted_workflow_sha="f" * 40,
            keyring=self.arguments["contract_keyring"],
            keys_directory=self.arguments["contract_keys_directory"],
            developer_directory=self.developer,
            tooling_evidence=self.tooling,
            tooling_public_key=self.tooling_key,
            java_executable=self.java,
            policy_revision="9" * 40,
            required_trust_domain="development",
            repository_root=self.root,
            environ={"SAFE": "environment"},
            token="token",
        )
        arguments.update(changes)
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                workflow.product_reuse,
                "_product_materialization_paths",
                return_value=(self.discovery, self.state, self.destination),
            ))
            stack.enter_context(patch.object(
                workflow.sdk_workflow,
                "verified_inputs",
                side_effect=self.verified_inputs,
            ))
            stack.enter_context(patch.object(
                workflow.product_reuse,
                "materialize_product_predecessors",
                side_effect=self.materialize,
            ))
            stack.enter_context(patch.object(workflow, "execute_package", side_effect=self.worker))
            stack.enter_context(patch.object(
                workflow.product_reuse,
                "finalize_phase_object",
                side_effect=self.finalize,
            ))
            stack.enter_context(patch.object(workflow, "verify_sdk_package_inputs", side_effect=self.gate))
            stack.enter_context(patch.object(workflow, "build_apple_package_execution_context",
                                            side_effect=self.execution_context))
            stack.enter_context(patch.object(
                workflow,
                "verify_phase_shard",
                side_effect=lambda *_: self.finalized,
            ))
            return workflow.execute(self.plan, self.discovery, self.state, self.destination, **arguments)

    def test_binary_gate_precedes_sdk_context_exit_and_publication(self):
        result = self.invoke()
        self.assertEqual(self.finalized, result)
        self.assertEqual(
            ["sdk-enter", "materialize", "worker", "finalize", "gate", "capture-context", "sdk-exit", "sdk-closed"],
            self.events,
        )
        self.assertTrue((self.destination / "shard").is_dir())
        self.assertTrue((self.destination / "apple-package-execution.json").is_file())
        self.assertFalse((self.destination / "shard/apple-package-execution.json").exists())
        retained_plan = self.destination / "original-plan/impact-plan.json"
        self.assertEqual(self.plan_bytes, retained_plan.read_bytes())
        self.assertFalse((self.destination / "shard/original-plan").exists())

    def test_optional_apple_policy_reaches_both_state_replay_seams_only(self):
        policy = {"caller": "external Apple policy"}
        result = self.invoke(sdk_apple_validation_policy=policy)
        self.assertEqual(self.finalized, result)
        self.assertNotIn("sdkAppleValidationPolicy", (self.destination / "original-plan/impact-plan.json").read_text())

    def test_metadata_admissions_reach_both_replay_seams_without_serialization(self):
        admissions = {"sdk_facade_metadata_admission": object(),
                      "sdk_android_metadata_admission": object()}
        result = self.invoke(**admissions)
        self.assertEqual(self.finalized, result)
        retained = (self.destination / "original-plan/impact-plan.json").read_bytes()
        context = (self.destination / "apple-package-execution.json").read_bytes()
        for name in admissions:
            self.assertNotIn(name.encode(), retained)
            self.assertNotIn(name.encode(), context)

    def test_current_contract_receipt_must_match_authenticated_sdk_inputs(self):
        self.contract_mismatch = True
        with self.assertRaisesRegex(ValueError, "Current Contract predecessor differs"):
            self.invoke()
        self.assertNotIn("worker", self.events)
        self.assertFalse((self.destination / "shard").exists())

    def test_gate_failure_never_publishes(self):
        self.gate_failure = True
        with self.assertRaisesRegex(ValueError, "full package rejection"):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())

    def test_stage_or_predecessor_mutation_after_sdk_exit_rejects_publication(self):
        for mutation, message in (
            ("sdk", "candidate changed after admission"),
            ("sdk-prepared", "changed after SDK verification"),
            ("capture", "original execution capture changed before publication"),
            ("capture-context", "original execution capture changed before publication"),
        ):
            self.destination = self.root / "build" / mutation
            self.events.clear()
            self.context_failure = mutation
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                self.invoke()
            self.assertFalse((self.destination / "shard").exists())

    def test_source_or_retained_plan_mutation_on_sdk_context_exit_rejects_publication(self):
        for mutation in ("source-plan", "retained-plan"):
            self.destination = self.root / "build" / mutation
            self.events.clear()
            self.context_failure = mutation
            try:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())
            finally:
                self.plan.write_bytes(self.plan_bytes)

    def test_developer_directory_is_required_normalized_and_unchanged(self):
        for value in (
            self.root / "missing-developer",
            self.developer.parent / ".." / "Contents/Developer",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.invoke(developer_directory=value)
            self.assertNotIn("worker", self.events)


if __name__ == "__main__":
    unittest.main()

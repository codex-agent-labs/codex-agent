"""Real receipt/shard/context pairing with mocked hosted, Git and semantic authority.

These orchestration fixtures do not establish signatures, original Git source,
native execution, or hosted phase admission.
"""

from contextlib import contextmanager, ExitStack
from copy import deepcopy
import io
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

from ci import sdk_ios_original_validation as workflow
from ci.tests import test_sdk_ios_original_package as fixtures
from ci.tests.product_chain_support import write_receipt
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file, snapshot_regular_tree, write_canonical_json
from products.plan import _upstream_record
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


class SdkIosOriginalValidationTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SdkIosOriginalPackageTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.root = fixture, fixture.root
        self.producer = {**fixture.producer, "commit": "c" * 40, "tree": "d" * 40, "runId": 92}
        self.template = self.root / "validation-upload"
        original = self.template / "original"
        self.stage = self.root / "validation-stage"
        content = self.stage / "outputs/validation/apple-validation.json"
        content.parent.mkdir(parents=True)
        content.write_bytes(b'{"synthetic":"semantic content"}\n')
        manifest = write_output_manifest(self.stage, "sdk", "sdk-ios", "validation", "ios-arm64", "0.8.0",
            {"apple-validation-content": "outputs/validation"})
        selected = write_receipt(self.root / "selected-validation.json", product="sdk", component="sdk-ios",
            phase="validation", target="ios-arm64", version="0.8.0", version_identity="0.8.0",
            outputs=manifest["outputs"], upstream=[_upstream_record(fixture.receipt)], context={"producer": self.producer})
        self.phase = {name: selected[name] for name in PHASE_PLAN_KEYS}
        finalized = finalize_phase_object(stage_root=self.stage, phase_plan=self.phase, producer=self.producer,
            product_version="0.8.0", trust_domain="development", destination=original / "shard")
        self.receipt, self.raw = finalized["receipt"], finalized["receiptBytes"]
        self.receipt_path = self.root / "validation-receipt.json"
        self.receipt_path.write_bytes(self.raw)
        selection = original / "selection"
        selection.mkdir()
        (selection / "impact-plan.json").write_bytes(fixture.plan.read_bytes())
        write_canonical_json(selection / "phase-plan.json", self.phase)
        write_canonical_json(selection / "producer.json", self.producer)
        self.captures = {"package": fixture.upload}
        (fixture.upload / "transport.zip").write_bytes(b"exact package ZIP\n")
        for name in ("sdk", "binary"):
            capture = self.root / f"{name}-capture"
            (capture / "original").mkdir(parents=True)
            (capture / "original/payload.bin").write_bytes(f"original {name}\n".encode())
            (capture / "transport.zip").write_bytes(f"exact {name} ZIP\n".encode())
            self.captures[name] = capture
        for name, capture in self.captures.items():
            write_canonical_json(capture / "capture-transport.json", {"observation": "fresh"})
            snapshot_regular_tree(capture, original / "originals" / name, allow_empty=True)
            write_canonical_json(original / "originals" / name / "capture-transport.json", {"observation": "historical"})
        native = self.root / "native-capture"
        for name in ("archives", "lanes", "native-evidence", "plan"):
            (native / name).mkdir(parents=True)
            (native / name / "original.bin").write_bytes(f"native {name}\n".encode())
        self.native_transport = {"receiptSha256s": {"original": "sha256:" + "8" * 64}, "observed": ["fresh"]}
        write_canonical_json(native / "native-transport.json", self.native_transport)
        snapshot_regular_tree(native, original / "originals/native", allow_empty=True)
        write_canonical_json(original / "originals/native/native-transport.json",
                             {**self.native_transport, "observed": ["historical"]})
        self.captures["native"] = native
        archive = original / "execution/apple-validation-evidence.zip"
        archive.parent.mkdir()
        archive.write_bytes(b"original raw archive\x00\xff")
        module = Path("/original/checkout/codex-agent-runtime-ios")
        execution = module / "build/imported-sdk-validation" / self.producer["tree"] / "ios-arm64"
        self.execution_context = {
            "schemaVersion": 1, "producer": self.producer, "target": "ios-arm64",
            "packageArtifact": {"artifactId": 701, "artifactSha256": "sha256:" + "7" * 64},
            "binaryArtifact": {"artifactId": 702, "artifactSha256": "sha256:" + "6" * 64},
            "rustHost": "aarch64-apple-darwin", "developerDirectory": "/original/Xcode",
            "originalWorkingDirectory": str(module), "originalDeviceWorkDirectory": str(execution / "device-execution"),
            "originalTestApplicationDirectory": str(execution / "device-consumer/CodexAgentTestApp"),
            "evidenceSha256": sha256_file(archive),
        }
        write_canonical_json(original / "context/execution-context.json", self.execution_context)
        fields = {"codexAgent.product": "sdk", "codexAgent.component": "sdk-ios", "codexAgent.phase": "validation",
            "codexAgent.target": "ios-arm64", "codexAgent.sdkVersion": "0.8.0", "codexAgent.contractVersion": "0.2.0",
            "codexAgent.candidateTree": self.producer["tree"], "codexAgent.candidateCommit": self.producer["commit"],
            **{f"codexAgent.{name}": f"/original/private/{name}" for name in (
                "iosValidationPackageStage", "contractBinaryStage", "sdkCompatibilityFile",
                "iosValidationTestApplicationDirectory", "iosValidationCompilerConsumersDirectory")}}
        self.worker_record = {"schemaVersion": 1, "producer": self.producer, "buildKey": self.receipt["buildKey"],
            "command": workflow.product_reuse._runtime_worker_command(module.parent / "gradlew", fields, {}, build_directory="."),
            "returnCode": 0, "launchError": None, "elapsedNs": 123}
        write_canonical_json(original / "worker/execution.json", self.worker_record)
        (original / "worker/gradle.log").write_bytes(b"")
        self.arguments = dict(artifact_id=703, artifact_sha256="sha256:" + "5" * 64,
            trusted_workflow_sha="e" * 40, keyring=fixture.keyring, keys_directory=fixture.keys,
            repository_root=self.root, environ={"GITHUB_RUN_ID": "unrelated-current"}, token="mock-token",
            tooling_evidence=fixture.tooling, tooling_public_key=fixture.tooling_key, java_executable=fixture.java,
            policy_revision="f" * 40, required_trust_domain="release")
        self.events, self.mutation = [], None
        self.package_receipt = fixture.receipt
        self.validation_inventory = self.receipt["inputs"]["inventory"]

    def capture(self, plan, destination, **arguments):
        self.events.append("capture")
        self.assertEqual(self.fixture.plan, plan)
        self.assertEqual(self.raw, arguments["validation_receipt_path"].read_bytes())
        self.assertNotEqual(self.receipt_path, arguments["validation_receipt_path"])
        self.assertEqual((703, "sha256:" + "5" * 64), (arguments["artifact_id"], arguments["artifact_sha256"]))
        snapshot_regular_tree(self.template, destination, allow_empty=True)
        self.captured = destination
        original = destination / "original"
        if self.mutation in ("worker-key", "worker-exit", "worker-command", "worker-producer"):
            value = deepcopy(self.worker_record)
            if self.mutation == "worker-key": value["buildKey"] = "sha256:" + "0" * 64
            if self.mutation == "worker-exit": value["returnCode"] = True
            if self.mutation == "worker-command": value["command"].append("arbitraryTask")
            if self.mutation == "worker-producer": value["producer"]["runAttempt"] = 99
            write_canonical_json(original / "worker/execution.json", value)
        elif self.mutation == "phase-plan":
            write_canonical_json(original / "selection/phase-plan.json", {**self.phase, "buildKey": "sha256:" + "0" * 64})
        elif self.mutation == "extra":
            (original / "worker/extra.json").write_bytes(b"unselected")
        elif self.mutation in ("package-zip", "sdk-original", "binary-zip", "native-original"):
            relative = {"package-zip": "package/transport.zip", "sdk-original": "sdk/original/payload.bin",
                        "binary-zip": "binary/transport.zip", "native-original": "native/native-evidence/original.bin"}[self.mutation]
            (original / "originals" / relative).write_bytes(b"different original")

    def validate_plan(self, path, repository, *, expected_revision):
        self.assertEqual(self.root, repository)
        self.assertEqual(self.producer["commit"], expected_revision)
        self.assertEqual(self.fixture.plan.read_bytes(), path.read_bytes())
        return {"remoteBuildAuthorized": self.mutation != "unauthorized", "event": "pull_request"}

    def consumer(self, plan, environment):
        self.assertEqual({"GITHUB_RUN_ID": "92", "GITHUB_RUN_ATTEMPT": "2"}, environment)
        return {"producer": self.producer}

    @contextmanager
    def package(self, plan, receipt_path, **arguments):
        self.events.append("package-enter")
        self.assertEqual(self.fixture.plan, plan)
        self.assertEqual(self.fixture.receipt_bytes, receipt_path.read_bytes())
        if "package_capture" in arguments:
            self.captured = arguments["package_capture"].parent.parent.parent
            self.assertEqual(self.captured / "original/originals/sdk", arguments["sdk_capture"])
        else:
            self.assertEqual(701, arguments["artifact_id"])
        yield {"stage": self.root / "package-stage", "receipt": self.package_receipt,
               "receiptBytes": canonical_json_bytes(self.package_receipt), "original": self.fixture.upload / "original",
               "packageCapture": self.captures["package"], "sdkCapture": self.captures["sdk"],
               "sdk": {"directory": self.root / "sdk-inputs", "compatibility": {"contract": {"digest": "sha256:" + "4" * 64}}}}
        self.events.append("package-exit")
        if self.mutation == "package-exit":
            (self.captured / "original/worker/gradle.log").write_bytes(b"changed on exit")

    @contextmanager
    def binary(self, plan, receipt_path, **arguments):
        self.events.append("binary-enter")
        stage, path, _ = self.fixture.predecessors[("sdk", "binary")]
        self.assertEqual(path, receipt_path)
        if "binary_capture" in arguments:
            self.assertEqual(self.captured / "original/originals/binary", arguments["binary_capture"])
        else:
            self.assertEqual(702, arguments["artifact_id"])
        self.assertEqual("aarch64-apple-darwin", arguments["rust_host"])
        yield {"stage": stage, "receiptBytes": b"different binary receipt" if self.mutation == "binary-receipt" else path.read_bytes(),
               "binaryCapture": self.captures["binary"],
               "native": {"captureRoot": self.captures["native"], "transport": self.native_transport}}
        self.events.append("binary-exit")

    def git(self, root, operation, object_name):
        self.assertEqual((self.root, "rev-parse"), (root, operation))
        self.assertTrue(object_name.startswith(self.producer["commit"]))
        if self.mutation == "git-tree": return "0" * 40
        return self.producer["tree" if object_name.endswith("{tree}") else "commit"]

    def inventory(self, root, commit, instance):
        self.assertEqual((self.root, self.producer["commit"], workflow.PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")),
                         (root, commit, instance))
        return self.validation_inventory

    def planner(self, instance, **arguments):
        self.events.append("plan")
        self.assertEqual([self.fixture.receipt], arguments["upstream_receipts"])
        self.assertEqual(self.validation_inventory, arguments["inventory"])
        self.assertEqual(workflow.NOT_APPLICABLE_TOOLCHAIN_DIGEST, arguments["toolchain_profile_digest"])
        self.assertEqual(workflow.NOT_APPLICABLE_FLAGS_DIGEST, arguments["flags_digest"])
        self.assertNotIn("contract_projection", arguments)
        return {**self.phase, "buildKey": "sha256:" + "0" * 64} if self.mutation == "replan" else self.phase

    def replay(self, **arguments):
        self.events.append("replay")
        self.assertEqual(self.producer["commit"], arguments["source_revision"])
        self.assertNotEqual(self.fixture.producer["commit"], arguments["source_revision"])
        self.assertEqual(self.fixture.receipt, arguments["package_receipt"])
        self.assertEqual(self.root / "package-stage", arguments["package_stage"])
        self.assertEqual(self.execution_context, arguments["context"])
        self.assertEqual(self.captured / "original/execution/apple-validation-evidence.zip", arguments["evidence_archive"])
        self.assertEqual(self.fixture.predecessors[("contract", "binary")][0] / "outputs/evidence/canonical-api.json",
                         arguments["canonical_api"])
        if self.mutation == "replay": raise ValueError("complete replay failed")
        return {"ordinary": "content"}

    @contextmanager
    def context(self, *, retained=False):
        with ExitStack() as stack:
            for owner, name, options in (
                (workflow.product_reuse, "capture_sdk_ios_validation_upload", {"side_effect": AssertionError("network") if retained else self.capture}),
                (workflow.product_reuse, "_validate_plan", {"side_effect": self.validate_plan}),
                (workflow.product_reuse, "_consumer", {"side_effect": self.consumer}),
                (workflow, "verified_retained_ios_package" if retained else "verified_original_ios_package", {"side_effect": self.package}),
                (workflow, "verified_retained_ios_binary" if retained else "verified_original_ios_binary", {"side_effect": self.binary}),
                (workflow, "run_git", {"side_effect": self.git}),
                (workflow, "git_product_versions", {"return_value": {"sdk": "0.8.0"}}),
                (workflow, "phase_git_inventory", {"side_effect": self.inventory}),
                (workflow, "plan_phase", {"side_effect": self.planner}),
                (workflow, "verify_apple_validation_stage", {"side_effect": self.replay}),
            ):
                stack.enter_context(patch.object(owner, name, **options))
            arguments = self.arguments if not retained else {key: value for key, value in self.arguments.items()
                if key not in {"artifact_id", "artifact_sha256", "trusted_workflow_sha", "environ", "token"}}
            if retained:
                for name in ("verified_original_ios_package", "verified_original_ios_binary"):
                    stack.enter_context(patch.object(workflow, name, side_effect=AssertionError("network")))
            selected = (workflow.verified_retained_ios_validation(self.fixture.plan, self.receipt_path,
                        validation_capture=self.template, **arguments) if retained else
                        workflow.verified_original_ios_validation(self.fixture.plan, self.receipt_path, **arguments))
            with selected as value:
                yield value

    def retained_template(self):
        original = self.template / "original"
        for name in ("package", "binary"):
            locator = self.execution_context[f"{name}Artifact"]
            write_canonical_json(original / "originals" / name / "capture-transport.json",
                {"artifact": {"id": locator["artifactId"], "digest": locator["artifactSha256"]}})
        plan = self.template / "plan/impact-plan.json"
        plan.parent.mkdir(exist_ok=True)
        plan.write_bytes(self.fixture.plan.read_bytes())
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for row in regular_file_inventory(original, allow_empty=True):
                archive.writestr(row["relativePath"], (original / row["relativePath"]).read_bytes())
        (self.template / "transport.zip").write_bytes(raw.getvalue())
        write_canonical_json(self.template / "capture-transport.json", {
            "captureProducer": self.producer, "observed": [], "validationReceiptSha256": sha256_bytes(self.raw),
            "artifact": {"id": 703, "digest": sha256_bytes(raw.getvalue()),
                "name": f"codex-agent-sdk-worker-sdk-ios-validation-ios-arm64-{self.receipt['buildKey'].removeprefix('sha256:')}-"
                        f"{self.producer['tree']}-attempt-{self.producer['runAttempt']}"}})

    def test_retained_validation_replays_all_gates_without_network_or_rewriting(self):
        self.retained_template()
        before = regular_file_inventory(self.template, allow_empty=True)
        with self.context(retained=True) as value:
            self.assertEqual(self.raw, value["receiptBytes"])
            self.assertEqual(self.package_receipt, value["package"]["receipt"])
            self.assertEqual(canonical_json_bytes(self.package_receipt), value["package"]["receiptBytes"])
            self.assertEqual(self.root / "package-stage", value["package"]["stage"])
            self.assertEqual(["package-enter", "binary-enter", "plan", "replay"], self.events)
            self.assertEqual(before, regular_file_inventory(value["capture"], allow_empty=True))
        self.assertEqual(["binary-exit", "package-exit"], self.events[-2:])
        self.assertEqual(before, regular_file_inventory(self.template, allow_empty=True))

    def test_retained_validation_replay_replan_and_exit_mutations_reject(self):
        for mutation in ("replay", "replan", "binary-receipt", "package-exit", "source-exit"):
            self.retained_template()
            self.mutation = mutation
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with self.context(retained=True):
                    if mutation == "source-exit":
                        (self.template / "extra").write_bytes(b"changed")

    def test_real_restore_context_original_pairing_and_mixed_producer_lifetimes(self):
        before = self.receipt_path.read_bytes()
        with self.context() as value:
            self.assertEqual(self.raw, value["receiptBytes"])
            self.assertEqual(self.raw, value["receiptPath"].read_bytes())
            self.assertEqual(regular_file_inventory(self.stage), regular_file_inventory(value["stage"]))
            self.assertEqual(["capture", "package-enter", "binary-enter", "plan", "replay"], self.events)
            private = value["stage"]
        self.assertEqual(["binary-exit", "package-exit"], self.events[-2:])
        self.assertFalse(private.exists())
        self.assertEqual(before, self.receipt_path.read_bytes())

    def test_causal_wrong_originals_controls_worker_and_original_plan_reject(self):
        for mutation in ("phase-plan", "unauthorized", "extra", "worker-key", "worker-exit", "worker-command",
                         "worker-producer", "package-zip", "sdk-original", "binary-zip", "native-original",
                         "binary-receipt", "git-tree", "replan", "replay"):
            self.mutation = mutation
            self.events.clear()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with self.context():
                    self.fail("unverified original validation yielded")
            if mutation != "replay": self.assertNotIn("replay", self.events)

    def test_context_exit_or_consumer_mutation_rejects_and_removes_private_paths(self):
        for mutation in ("stage", "capture", "selected-receipt", "keyring", "package-exit"):
            self.mutation = mutation
            keyring = self.fixture.keyring.read_bytes()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with self.context() as value:
                    paths = {"stage": value["stage"] / "extra", "capture": value["capture"] / "extra",
                             "selected-receipt": value["receiptPath"], "keyring": self.fixture.keyring}
                    if mutation in paths: paths[mutation].write_bytes(b"changed during use")
            self.fixture.keyring.write_bytes(keyring)
            self.assertFalse(self.captured.exists())

    def test_real_planner_replay_binds_both_targets_source_inventory_and_package_outputs(self):
        # Only Git acquisition is mocked here; both expected-plan construction
        # and the reader's comparison invoke the actual registered planner.
        versions = {"contract": "0.2.0", "runtime-release": "0.8.1",
                    "runtime-compatibility": "0.8.0", "sdk": "0.8.0"}
        sources = self.root / "replan-source"
        source = sources / "codex-agent-runtime-ios/apple/Tests/Original.swift"
        source.parent.mkdir(parents=True)
        source_bytes = b"original source A\n"
        source.write_bytes(source_bytes)
        original_inventory = regular_file_inventory(sources)
        for target in ("ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                instance = workflow.PhaseInstanceId("sdk", "sdk-ios", "validation", target)
                planned = workflow.plan_phase(instance, inventory=original_inventory, versions=versions,
                    upstream_receipts=[self.fixture.receipt],
                    toolchain_profile_digest=workflow.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                    flags_digest=workflow.NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
                receipt = workflow.validate_phase_receipt({**self.receipt, **planned})
                with patch.object(workflow, "run_git", side_effect=self.git), \
                        patch.object(workflow, "git_product_versions", return_value=versions) as git_versions, \
                        patch.object(workflow, "phase_git_inventory", return_value=original_inventory) as git_inventory:
                    workflow._replan(self.root, instance, receipt, self.fixture.receipt)
                    git_versions.assert_called_with(self.root, self.producer["commit"])
                    git_inventory.assert_called_with(self.root, self.producer["commit"], instance)

                    source.write_bytes(source_bytes.replace(b"A", b"B"))
                    git_inventory.return_value = regular_file_inventory(sources)
                    with self.assertRaisesRegex(ValueError, "inputs/build key differ"):
                        workflow._replan(self.root, instance, receipt, self.fixture.receipt)
                    source.write_bytes(source_bytes)
                    git_inventory.return_value = original_inventory

                    package = deepcopy(self.fixture.receipt)
                    output = package["outputs"][0]
                    raw = (self.root / "package-stage" / output["relativePath"]).read_bytes()
                    output["sha256"] = sha256_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                    workflow.validate_phase_receipt(package)
                    with self.assertRaisesRegex(ValueError, "inputs/build key differ"):
                        workflow._replan(self.root, instance, receipt, package)


if __name__ == "__main__":
    unittest.main()

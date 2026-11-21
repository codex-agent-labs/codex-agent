"""Real receipt/shard/context pairing with mocked hosted, Git and semantic authority.

These orchestration fixtures do not establish signatures, original Git source,
native execution, or hosted phase admission.
"""

from contextlib import contextmanager, ExitStack
from copy import deepcopy
import io
import shutil
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
    def context(self, *, retained=False, **overrides):
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
            arguments = {**arguments, **overrides}
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
        for name in (("package", "binary") if (original / "originals/package").exists() else ()):
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

    def test_compact_original_and_retained_validation_require_native_authority(self):
        originals = self.template / "original/originals"
        shutil.rmtree(originals)
        compact = originals / "completed"
        compact.mkdir(parents=True)
        (compact / "package-receipt.json").write_bytes(canonical_json_bytes(self.package_receipt))
        (compact / "completed-package.json").write_bytes(b"synthetic native-bound controls")
        cap = object()  # Authority seam only; concrete native reader has separate byte tests.
        @contextmanager
        def native_inputs(plan, receipt_path, **arguments):
            self.assertIs(cap, arguments["completed_frozen"])
            self.captured = arguments["retained"].parent.parent.parent
            self.assertEqual(canonical_json_bytes(self.package_receipt), receipt_path.read_bytes())
            self.events.append("native-enter")
            yield {"stage": self.root / "package-stage", "receipt": self.package_receipt,
                "receiptBytes": canonical_json_bytes(self.package_receipt), "original": self.fixture.upload / "original",
                "sdk": {"directory": self.root / "sdk-inputs", "compatibility": {"contract": {"digest": "sha256:" + "4" * 64}}},
                **{name: self.execution_context[name] for name in ("packageArtifact", "binaryArtifact")}}
            self.events.append("native-exit")
        with patch.object(workflow, "verified_completed_ios_package", side_effect=native_inputs):
            for retained in (False, True):
                if retained:
                    self.retained_template()
                self.events.clear()
                with self.assertRaisesRegex(ValueError, "independently authenticated"), self.context(retained=retained):
                    pass
                self.events.clear()
                with self.context(retained=retained, completed_frozen=cap) as value:
                    self.assertEqual(self.raw, value["receiptBytes"])
                    self.assertNotIn("binary-enter", self.events)
                    self.assertIn("replay", self.events)
                self.assertEqual("native-exit", self.events[-1])

    def test_recovered_original_and_retained_readers_preserve_both_producers_and_replay(self):
        original = self.template / "original"
        shutil.rmtree(original / "originals")
        compact = original / "originals/completed"
        compact.mkdir(parents=True)
        (compact / "package-receipt.json").write_bytes(canonical_json_bytes(self.package_receipt))
        (compact / "completed-package.json").write_bytes(b"fixture native controls")
        for name in ("execution", "context", "worker"):
            shutil.rmtree(original / name)
        origin = {"fixture": "historical origin, never authority", "producer": self.fixture.producer}
        write_canonical_json(original / "recovery/origin.json", origin)
        (original / "recovery/production-worker.zip").write_bytes(b"retained whole original")
        write_canonical_json(original / "recovery/replay.json", {"schemaVersion": 1, "producer": self.producer,
            "buildKey": self.receipt["buildKey"], "originSha256": sha256_bytes(canonical_json_bytes(origin))})
        cap = object()
        @contextmanager
        def native_inputs(plan, path, **kwargs):
            self.assertIs(cap, kwargs["completed_frozen"])
            yield {"stage": self.root / "package-stage", "receipt": self.package_receipt,
                "receiptBytes": canonical_json_bytes(self.package_receipt), "original": self.fixture.upload / "original",
                "completedCapture": kwargs["retained"],
                "sdk": {"directory": self.root / "sdk-inputs", "compatibility": {"contract": {"digest": "sha256:" + "4" * 64}}}}
        @contextmanager
        def recovery(plan, consumer, phase, selected_origin, archive, **kwargs):
            self.assertEqual(self.producer, consumer)
            self.assertEqual(self.phase, phase)
            self.assertEqual(origin, selected_origin)
            self.assertEqual(b"retained whole original", archive.read_bytes())
            self.assertNotIn("download", kwargs)
            self.events.append("origin-enter")
            yield {"producer": self.fixture.producer, "context": self.execution_context,
                "evidenceArchive": self.root / "private-historical-evidence.zip"}
            self.events.append("origin-exit")
            if self.mutation == "origin-exit":
                raise ValueError("historical origin exit rejected")
        def replay(**kwargs):
            self.assertEqual(self.fixture.producer["commit"], kwargs["source_revision"])
            self.assertEqual(self.root / "private-historical-evidence.zip", kwargs["evidence_archive"])
            self.assertEqual(self.execution_context, kwargs["context"])
            self.events.append("full-replay")
            if self.mutation == "replay":
                raise ValueError("full recovered replay rejected")
        self.replay = replay
        with patch.object(workflow, "verified_completed_ios_package", side_effect=native_inputs), \
                patch.object(workflow, "verified_validation_recovery", side_effect=recovery):
            for retained in (False, True):
                if retained:
                    self.retained_template()
                self.events.clear()
                with self.context(retained=retained, completed_frozen=cap) as value:
                    self.assertEqual(self.producer, value["receipt"]["producer"])
                self.assertEqual(["origin-enter", "plan", "full-replay", "origin-exit"],
                    [event for event in self.events if event != "capture"])
                for mutation in ("replay", "origin-exit"):
                    self.mutation = mutation
                    with self.assertRaisesRegex(ValueError, "rejected"), self.context(retained=retained, completed_frozen=cap):
                        pass
                self.mutation = None
        write_canonical_json(original / "recovery/replay.json", {"producer": self.fixture.producer})
        with patch.object(workflow, "verified_completed_ios_package", side_effect=native_inputs), \
                patch.object(workflow, "verified_validation_recovery") as gate, \
                self.assertRaisesRegex(ValueError, "actual verification producer"), self.context(completed_frozen=cap):
            pass
        gate.assert_not_called()

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

    def test_dependency_seed_is_retained_but_never_authority_and_remains_immutable(self):
        seed = self.template / "original/worker-dependency-seed/resolve-dependencies.gradle"
        seed.parent.mkdir()
        seed.write_bytes(b"throw new AssertionError('diagnostic seed must never run')\n")
        archive = self.root / "same-job.zip"
        with patch.object(self, "capture", wraps=self.capture) as capture:
            with self.context(validation_archive=archive) as value:
                retained = value["capture"] / "original/worker-dependency-seed/resolve-dependencies.gradle"
                self.assertEqual(seed.read_bytes(), retained.read_bytes())
                self.assertIn("replay", self.events)
            self.assertEqual(archive, capture.call_args.kwargs["transport_archive"])
        with self.assertRaisesRegex(ValueError, "changed"), self.context() as value:
            (value["capture"] / "original/worker-dependency-seed/resolve-dependencies.gradle").write_bytes(b"changed")


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



class ReferenceOnlyPackageValidationTest(unittest.TestCase):
    """M replays V carriers that name P only by its authenticated upload locator."""

    def setUp(self):
        base = SdkIosOriginalValidationTest(methodName="test_retained_validation_replays_all_gates_without_network_or_rewriting")
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.base = base

    def __getattr__(self, name):
        if name == "base":
            raise AttributeError(name)
        return getattr(self.base, name)

    def reference_template(self, receipt_bytes=None, reference_changes=None):
        package = self.template / "original/originals/package"
        shutil.rmtree(package)
        raw = self.fixture.receipt_bytes if receipt_bytes is None else receipt_bytes
        receipt = workflow.load_canonical_json_bytes(raw)
        locator = self.execution_context["packageArtifact"]
        transport = {"artifact": {"id": locator["artifactId"], "digest": locator["artifactSha256"]},
                     "captureProducer": receipt["producer"], "packageReceiptSha256": sha256_bytes(raw)}
        write_canonical_json(package / "capture-transport.json", {**transport, "observed": ["historical"]})
        shard = package / "original/shard"
        shard.mkdir(parents=True)
        (shard / "phase-receipt.json").write_bytes(raw)
        (shard / "phase-object.json").write_bytes(
            (self.fixture.upload / "original/shard/phase-object.json").read_bytes())
        write_canonical_json(package / workflow.PACKAGE_REFERENCE_NAME, {"schemaVersion": 1,
            "packageArtifact": dict(locator), "packageReceiptSha256": sha256_bytes(raw),
            "packageBuildKey": receipt["buildKey"], "packageProducer": receipt["producer"],
            **(reference_changes or {})})
        # The fresh recapture carries fresh observations but the same identity.
        write_canonical_json(self.fixture.upload / "capture-transport.json", {**transport, "observed": ["fresh"]})
        self.base.retained_template()
        # retained_template() normalizes legacy locators; restore V's full P transport and re-seal.
        write_canonical_json(package / "capture-transport.json", {**transport, "observed": ["historical"]})
        self.reseal()

    def reseal(self):
        original = self.template / "original"
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            for row in regular_file_inventory(original, allow_empty=True):
                archive.writestr(row["relativePath"], (original / row["relativePath"]).read_bytes())
        (self.template / "transport.zip").write_bytes(raw.getvalue())
        transport = workflow.load_canonical_json_bytes((self.template / "capture-transport.json").read_bytes())
        transport["artifact"]["digest"] = sha256_bytes(raw.getvalue())
        write_canonical_json(self.template / "capture-transport.json", transport)

    def recapture(self, plan, receipt_path, **arguments):
        self.assertNotIn("package_capture", arguments)
        self.assertEqual(("e" * 40, "mock-token"), (arguments["trusted_workflow_sha"], arguments["token"]))
        self.assertNotIn(self.template, receipt_path.parents)
        return self.base.package(plan, receipt_path, **arguments)

    def binary(self, plan, receipt_path, **arguments):
        self.base.captured = arguments["binary_capture"].parent.parent.parent
        return self.base.binary(plan, receipt_path, **arguments)

    @contextmanager
    def reference_replay(self, recapture=None):
        base = self.base
        with ExitStack() as stack:
            for owner, name, options in (
                (workflow.product_reuse, "capture_sdk_ios_validation_upload", {"side_effect": AssertionError("network")}),
                (workflow.product_reuse, "_validate_plan", {"side_effect": base.validate_plan}),
                (workflow.product_reuse, "_consumer", {"side_effect": base.consumer}),
                (workflow, "verified_retained_ios_package", {"side_effect": AssertionError("V payload")}),
                (workflow, "verified_original_ios_package", {"side_effect": recapture or self.recapture}),
                (workflow, "verified_retained_ios_binary", {"side_effect": self.binary}),
                (workflow, "verified_original_ios_binary", {"side_effect": AssertionError("network")}),
                (workflow, "run_git", {"side_effect": base.git}),
                (workflow, "git_product_versions", {"return_value": {"sdk": "0.8.0"}}),
                (workflow, "phase_git_inventory", {"side_effect": base.inventory}),
                (workflow, "plan_phase", {"side_effect": base.planner}),
                (workflow, "verify_apple_validation_stage", {"side_effect": self.replay}),
            ):
                stack.enter_context(patch.object(owner, name, **options))
            arguments = {key: value for key, value in base.arguments.items()
                         if key not in {"artifact_id", "artifact_sha256", "trusted_workflow_sha", "environ", "token"}}
            yield lambda: workflow.verified_retained_ios_validation(base.fixture.plan, base.receipt_path,
                                                                     validation_capture=base.template, **arguments)

    def replay(self, **arguments):
        self.base.captured = arguments["evidence_archive"].parent.parent.parent
        return self.base.replay(**arguments)

    def policy(self, **changes):
        return {**{key: value for key, value in self.arguments.items() if key in {
            "keyring", "keys_directory", "repository_root", "tooling_evidence", "tooling_public_key",
            "java_executable", "policy_revision", "required_trust_domain"}}, **changes}

    def test_same_package_under_a_different_caller_policy_is_rejected(self):
        path = self.root / "p.json"
        path.write_bytes(self.fixture.receipt_bytes)
        locator = {"artifactId": 701, "artifactSha256": "sha256:" + "7" * 64}
        with patch.object(workflow, "verified_original_ios_package", side_effect=self.recapture), \
                self.authority():
            workflow._recaptured_reference_package(self.fixture.plan, path, locator, **self.policy())
            self.assertIs(workflow._recaptured_reference_package(self.fixture.plan, path, locator, **self.policy())["receipt"],
                          self.package_receipt)
            with self.assertRaisesRegex(ValueError, "different caller policy"):
                workflow._recaptured_reference_package(self.fixture.plan, path, locator,
                                                       **self.policy(policy_revision="0" * 40))
        self.assertEqual(1, self.events.count("package-enter"))

    def test_authority_without_token_is_a_no_op_when_no_reference_only_v_is_replayed(self):
        # sdk-completion/collectors may enter the authority for every run; legacy and
        # natively completed carriers never touch it, so no token or download is needed.
        self.base.retained_template()
        with self.authority(token=None), self.base.context(retained=True) as value:
            self.assertEqual(self.raw, value["receiptBytes"])
        self.assertEqual(1, self.events.count("package-enter"))

    def test_hosted_recapture_refuses_before_download_when_capacity_is_insufficient(self):
        self.reference_template()
        from types import SimpleNamespace
        import io
        from contextlib import redirect_stderr
        with patch("runtime_reference_transport.native_clone_capable", return_value=False), \
                patch("runtime_reference_transport.shutil.disk_usage", return_value=SimpleNamespace(free=14 * 10**9)), \
                redirect_stderr(io.StringIO()), self.reference_replay() as replay, \
                workflow.package_reference_recapture(trusted_workflow_sha="e" * 40,
                    environ={"GITHUB_ACTIONS": "true"}, token="mock-token"), \
                self.assertRaisesRegex(ValueError, "Insufficient free space for apple-package-reference-recapture-byte-copy"):
            with replay():
                pass
        self.assertNotIn("package-enter", self.events)
        self.assertEqual(4 * 19_941_206_953 + 46 * 1024**3,
                         workflow.package_recapture_required_free_bytes(19_941_206_953, clones=False))

    def test_collector_holds_one_wave_wide_authority_around_sequential_apple_rows(self):
        import ast
        import inspect
        from ci import product_reuse
        source = inspect.getsource(product_reuse.collect_runtime_workers)
        self.assertEqual(1, source.count("package_reference_recapture("))
        tree = ast.parse("def wrapper():\n" + "\n".join("    " + line for line in source.splitlines()))
        withs = [node for node in ast.walk(tree) if isinstance(node, ast.With)
                 and "package_reference_recapture" in ast.unparse(node.items[0].context_expr)]
        self.assertEqual(1, len(withs))
        self.assertIn("ordered", ast.unparse(withs[0].items[-1].optional_vars))
        self.assertIn('"ios-validation", "ios-metadata"', source)

    def authority(self, token="mock-token"):
        return workflow.package_reference_recapture(trusted_workflow_sha="e" * 40, environ={}, token=token)

    def test_reference_only_carrier_recaptures_p_once_for_both_targets_and_admissions(self):
        self.reference_template()
        before = regular_file_inventory(self.template, allow_empty=True)
        with self.reference_replay() as replay, self.authority():
            for _ in range(3):  # device, simulator and the later admission replay
                with replay() as value:
                    self.assertEqual(canonical_json_bytes(self.package_receipt), value["package"]["receiptBytes"])
            self.assertEqual(1, self.events.count("package-enter"))
            self.assertNotIn("package-exit", self.events)
        self.assertEqual("package-exit", self.events[-1])
        self.assertEqual(before, regular_file_inventory(self.template, allow_empty=True))

    def test_reference_only_carrier_without_caller_authority_is_rejected_before_download(self):
        self.reference_template()
        with self.reference_replay() as replay, \
                self.assertRaisesRegex(ValueError, "requires caller package recapture authority"):
            with replay():
                pass
        self.assertNotIn("package-enter", self.events)

    def test_reference_receipt_differing_from_validation_lineage_is_rejected(self):
        outputs = deepcopy(self.package_receipt["outputs"])
        outputs[0]["sha256"] = "sha256:" + "0" * 64
        other = write_receipt(self.root / "other-package.json", product="sdk", component="sdk-ios",
            phase="package", target="ios", version="0.8.0", version_identity="0.8.0", outputs=outputs,
            upstream=[], context={"producer": self.fixture.producer})
        self.reference_template(canonical_json_bytes(other))
        with self.reference_replay() as replay, self.authority(), \
                self.assertRaisesRegex(ValueError, "differs from its validation lineage"):
            with replay():
                pass
        self.assertNotIn("package-enter", self.events)

    def test_reference_digest_build_key_producer_or_locator_mismatch_is_rejected(self):
        for field, value in (("packageReceiptSha256", "sha256:" + "0" * 64),
                             ("packageBuildKey", "sha256:" + "0" * 64),
                             ("packageProducer", {**self.fixture.producer, "runId": 1}),
                             ("packageArtifact", {"artifactId": 999, "artifactSha256": "sha256:" + "7" * 64})):
            self.base.setUp()
            self.reference_template(reference_changes={field: value})
            with self.subTest(field=field), self.reference_replay() as replay, self.authority(), \
                    self.assertRaisesRegex(ValueError, "differs from its receipt or validation locator"):
                with replay():
                    pass
            self.assertNotIn("package-enter", self.events)

    def test_recapture_differing_from_retained_small_members_is_rejected(self):
        for member in ("original/shard/phase-object.json", "capture-transport.json"):
            self.base.setUp()
            self.reference_template()
            target = self.fixture.upload / member
            if member == "capture-transport.json":
                write_canonical_json(target, {"artifact": {"id": 1, "digest": "sha256:" + "1" * 64}})
            else:
                target.write_bytes(b'{"different":"object"}')
            with self.subTest(member=member), self.reference_replay() as replay, self.authority(), \
                    self.assertRaisesRegex(ValueError, "Recaptured Apple package .*differs from its retained"):
                with replay():
                    pass

    def test_recaptured_receipt_or_digest_mismatch_is_rejected(self):
        self.reference_template()

        @contextmanager
        def different(plan, receipt_path, **arguments):
            with self.recapture(plan, receipt_path, **arguments) as value:
                yield {**value, "receiptBytes": b"different recaptured receipt"}
        with self.reference_replay(different) as replay, self.authority(), \
                self.assertRaisesRegex(ValueError, "Recaptured Apple package differs"):
            with replay():
                pass

    def test_expired_or_unauthenticated_upload_fails_closed_and_is_not_held(self):
        self.reference_template()
        failures = []

        def expired(plan, receipt_path, **arguments):
            failures.append(arguments["artifact_id"])
            raise ValueError("Contract uploaded artifact differs from the caller-bound transport identity")
        with self.reference_replay(expired) as replay, self.authority():
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "caller-bound transport identity"):
                    with replay():
                        pass
        self.assertEqual([701, 701], failures)

    def test_missing_token_fails_before_any_recapture(self):
        self.reference_template()
        with self.reference_replay() as replay, self.authority(token=None), \
                self.assertRaisesRegex(ValueError, "observation token"):
            with replay():
                pass
        self.assertNotIn("package-enter", self.events)

    def test_carrier_with_both_payload_and_reference_or_wrong_locator_is_rejected(self):
        self.base.retained_template()
        write_canonical_json(self.template / "original/originals/package" / workflow.PACKAGE_REFERENCE_NAME, {})
        self.base.retained_template()
        with self.reference_replay() as replay, self.authority(), \
                self.assertRaisesRegex(ValueError, "unexpected layout"):
            with replay():
                pass
        with self.assertRaisesRegex(ValueError, "pinned caller workflow"):
            with workflow.package_reference_recapture(trusted_workflow_sha="latest", environ={}, token="t"):
                pass
        path = self.root / "p.json"
        path.write_bytes(self.fixture.receipt_bytes)
        policy = self.policy()
        with patch.object(workflow, "verified_original_ios_package", side_effect=self.recapture), \
                self.authority(), self.assertRaisesRegex(ValueError, "different original packages"):
            workflow._recaptured_reference_package(self.fixture.plan, path,
                {"artifactId": 701, "artifactSha256": "sha256:" + "7" * 64}, **policy)
            workflow._recaptured_reference_package(self.fixture.plan, path,
                {"artifactId": 999, "artifactSha256": "sha256:" + "7" * 64}, **policy)


class PackageReferenceLayoutAgreementTest(unittest.TestCase):
    def test_reader_constants_equal_the_v_writer(self):
        from ci import sdk_ios_validation_workflow as writer
        self.assertEqual(writer.PACKAGE_REFERENCE_NAME, workflow.PACKAGE_REFERENCE_NAME)
        self.assertEqual(writer.PACKAGE_REFERENCE_MEMBERS, workflow.PACKAGE_REFERENCE_MEMBERS)

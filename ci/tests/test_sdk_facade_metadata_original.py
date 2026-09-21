"""Real writer, shard, held join and planner; observation/Git/compiler are mocked.

These fixtures provide no genuine hosted, signing or native-execution evidence.
"""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from ci import sdk_facade_metadata_original as original
from ci.tests import test_sdk_facade_metadata_workflow as fixtures
from products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree, sha256_bytes
from products.registry import SDK_FACADE_TARGETS


class FacadeMetadataOriginalTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeMetadataWorkflowTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.versions = {"sdk": "0.8.7", "contract": "0.2.0", "runtime-release": "0.8.1", "runtime-compatibility": "0.8.0"}
        source = self.root / "source-inventory"
        source.mkdir()
        (source / "metadata.py").write_bytes(b"original metadata source\n")
        self.inventory = regular_file_inventory(source)
        self.validation_receipts = {target: {"receipt": self.f.f.f.originals[target]} for target in SDK_FACADE_TARGETS}
        planned = original.plan_phase(original._INSTANCE, inventory=self.inventory, versions=self.versions,
            upstream_receipts=[self.validation_receipts[target]["receipt"] for target in SDK_FACADE_TARGETS],
            toolchain_profile_digest=original.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=original.NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
        self.f.ready = planned
        self.f.election.return_value.prior_ready_plans = {original._INSTANCE: planned}
        produced = fixtures.workflow.execute(**self.f.arguments())
        self.receipt_path = self.root / "selected-metadata.json"
        self.receipt_path.write_bytes(produced["shard"]["receiptBytes"])
        self.receipt = produced["shard"]["receipt"]
        # Independently supplied fixture policy, not recovered from execution JSON.
        self.context = {"repositoryRoot": "/original/checkout", "metadataRequest": "/original-private/metadata-request.json"}
        worker = self.f.destination / "worker/execution.json"
        execution = original._json(worker)
        fields = {"codexAgent.product": "sdk", "codexAgent.component": "sdk-core", "codexAgent.phase": "metadata",
            "codexAgent.target": "common", "codexAgent.sdkVersion": "0.8.7",
            "codexAgent.candidateCommit": self.receipt["producer"]["commit"],
            "codexAgent.candidateTree": self.receipt["producer"]["tree"],
            "codexAgent.sdkFacadeMetadataRequest": self.context["metadataRequest"]}
        execution.update(workingDirectory=self.context["repositoryRoot"], command=original.product_reuse._runtime_worker_command(
            "/original/checkout/gradlew", fields, {}, build_directory=".", platform_name="posix"))
        worker.write_bytes(canonical_json_bytes(execution))
        self.capture_mutation = None
        self.capture = self.enterContext(patch.object(original, "capture_sdk_facade_metadata_upload", side_effect=self.capture_upload))
        self.plan = self.enterContext(patch.object(original.product_reuse, "_validate_plan",
            return_value={"remoteBuildAuthorized": True, "event": "pull_request"}))
        self.enterContext(patch.object(original.product_reuse, "_consumer", return_value={"producer": self.receipt["producer"]}))
        self.enterContext(patch.object(original, "run_git", side_effect=lambda root, op, revision:
            self.receipt["producer"]["tree" if revision.endswith("{tree}") else "commit"] + "\n"))
        self.enterContext(patch.object(original, "git_product_versions", return_value=self.versions))
        self.git_inventory = self.enterContext(patch.object(original, "phase_git_inventory", return_value=self.inventory))
        self.held = self.enterContext(patch.object(original, "verified_facade_metadata_inputs", side_effect=self.f.f.call))
        self.enterContext(patch.object(original, "_request_inventory",
            side_effect=lambda path: {path: original.sha256_file(path)}))

    def capture_upload(self, plan, destination, **kwargs):
        self.assertEqual(self.receipt_path.read_bytes(), kwargs["metadata_receipt_path"].read_bytes())
        self.assertEqual(123, kwargs["artifact_id"])
        self.assertEqual("explicit-caller-token", kwargs["token"])
        snapshot_regular_tree(self.f.destination, destination / "original", allow_empty=True)
        (destination / "plan").mkdir()
        (destination / "plan/impact-plan.json").write_bytes(plan.read_bytes())
        (destination / "transport.zip").write_bytes(b"opaque uploaded ZIP; capture boundary mocked")
        transport = {"metadataReceiptSha256": sha256_bytes(self.receipt_path.read_bytes()),
            "captureProducer": deepcopy(self.receipt["producer"]), "artifact": {"id": 123}, "observed": []}
        (destination / "capture-transport.json").write_bytes(canonical_json_bytes(transport))
        if self.capture_mutation:
            self.capture_mutation(destination / "original")
        return transport

    def call(self, **changes):
        arguments = self.f.arguments()
        for name in ("discovery", "state", "destination", "expected_build_key"):
            arguments.pop(name)
        arguments.update(metadata_receipt_path=self.receipt_path, artifact_id=123,
            artifact_sha256="sha256:" + "d" * 64, original_context=self.context)
        arguments.update(changes)
        return original.verified_original_sdk_facade_metadata(**arguments)

    def prepare_retained(self):
        self.retained = self.root / "caller-authenticated-metadata-capture"
        # Build real ZIP/shard consistency; no assertion of official observation.
        self.capture_upload(self.f.f.plan, self.retained,
            metadata_receipt_path=self.receipt_path, artifact_id=123, token="explicit-caller-token")
        with zipfile.ZipFile(self.retained / "transport.zip", "w") as archive:
            for row in regular_file_inventory(self.retained / "original", allow_empty=True):
                name = row["relativePath"]
                archive.writestr(name, (self.retained / "original" / name).read_bytes())
        transport = original._json(self.retained / "capture-transport.json")
        producer = self.receipt["producer"]
        transport["artifact"] = {"id": 123, "digest": original.sha256_file(self.retained / "transport.zip"),
            "name": f"codex-agent-sdk-worker-sdk-core-metadata-common-{self.receipt['buildKey'].removeprefix('sha256:')}-"
                    f"{producer['tree']}-attempt-{producer['runAttempt']}"}
        (self.retained / "capture-transport.json").write_bytes(canonical_json_bytes(transport))
        for target, record in self.f.f.records.items():
            capture = self.root / ("retained-validation-" + target)
            snapshot_regular_tree(self.f.destination / "originals/validations" / target / "capture",
                                  capture, allow_empty=True)
            self.f.f.records[target] = {key: value for key, value in record.items()
                if key in {"validationReceipt", "facadeRequest", "nativeCompilerArchive"}}
            self.f.f.records[target]["captureRoot"] = capture
        self.no_network = self.enterContext(patch("reuse.api_request",
            side_effect=AssertionError("retained metadata replay must not perform network acquisition")))

    def retained_call(self, **changes):
        arguments = self.f.arguments()
        for name in ("discovery", "state", "destination", "expected_build_key", "token", "trusted_workflow_sha"):
            arguments.pop(name)
        arguments.update(metadata_receipt_path=self.receipt_path, capture_root=self.retained,
                         original_context=self.context)
        arguments.update(changes)
        return original.verified_retained_sdk_facade_metadata(**arguments)

    def test_retained_metadata_is_offline_and_holds_all_eleven_full_gates(self):
        self.prepare_retained()
        before = regular_file_inventory(self.retained, allow_empty=True)
        with self.retained_call() as value:
            self.assertEqual(set(SDK_FACADE_TARGETS), self.f.f.active)
            self.assertEqual(self.receipt_path.read_bytes(), value["receiptBytes"])
            self.assertEqual(before, regular_file_inventory(value["capture"], allow_empty=True))
            self.assertNotEqual(self.retained, value["capture"])
            self.assertEqual({"stage", "receiptPath", "receiptBytes", "receipt", "capture", "original", "transport"}, set(value))
            private = value["capture"]
        self.assertFalse(private.exists())
        self.assertFalse(self.f.f.active)
        self.assertEqual(before, regular_file_inventory(self.retained, allow_empty=True))
        self.capture.assert_not_called()
        self.no_network.assert_not_called()

    def test_retained_metadata_rejects_live_predecessors_or_transport_substitution(self):
        self.prepare_retained()
        records = deepcopy(self.f.f.records)
        records["jvm"].pop("captureRoot")
        records["jvm"].update(artifactId=1, artifactSha256="sha256:" + "a" * 64)
        with self.assertRaisesRegex(ValueError, "all eleven"), self.retained_call(validations=records):
            self.fail("retained metadata must not fall back to network")
        self.held.assert_not_called()
        archive = self.retained / "transport.zip"
        archive.write_bytes(archive.read_bytes() + b"altered original ZIP")
        with self.assertRaisesRegex(ValueError, "original digest"), self.retained_call():
            self.fail("changed archive yielded")
        self.held.assert_not_called()
        self.capture.assert_not_called()
        self.no_network.assert_not_called()

    def test_retained_metadata_full_replay_failure_and_exit_failure_remain_mandatory(self):
        self.prepare_retained()
        before = self.git_inventory.return_value
        self.git_inventory.return_value = [{**self.inventory[0], "sha256": "sha256:" + "e" * 64}]
        with self.assertRaisesRegex(ValueError, "original source/version/phase key"), self.retained_call():
            self.fail("source replan bypassed")
        self.git_inventory.return_value = before
        self.f.f.exit_failure = "jvm"
        with self.assertRaisesRegex(ValueError, "reader exit rejected"), self.retained_call():
            pass
        self.capture.assert_not_called()

    def test_retained_metadata_source_private_and_caller_mutations_reject(self):
        self.prepare_retained()
        with self.assertRaisesRegex(ValueError, "changed"), self.retained_call() as value:
            (value["original"] / "worker/gradle.log").write_bytes(b"private mutation")
        with self.assertRaisesRegex(ValueError, "changed"), self.retained_call() as value:
            value["receipt"]["producer"]["runAttempt"] += 1
        with self.assertRaisesRegex(ValueError, "changed"), self.retained_call():
            self.f.f.archive.write_bytes(b"independent policy mutation")
        # Archive baseline is established anew on the next independent replay;
        # deep native authentication remains explicitly mocked in this fixture.
        with self.assertRaisesRegex(ValueError, "changed"), self.retained_call():
            (self.retained / "original/worker/gradle.log").write_bytes(b"caller capture mutation")

    def test_retained_metadata_snapshot_and_ancestry_are_not_implicit_authority(self):
        self.prepare_retained()
        symbolic = self.root / "symbolic-capture"
        symbolic.symlink_to(self.retained, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symbolic"), self.retained_call(capture_root=symbolic):
            pass
        snapshot = original.snapshot_regular_tree
        def mutate(source, destination, **kwargs):
            result = snapshot(source, destination, **kwargs)
            if source == self.retained:
                (destination / "original/worker/gradle.log").write_bytes(b"snapshot mutation")
            return result
        with patch.object(original, "snapshot_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during snapshot"), self.retained_call():
            pass
        self.held.assert_not_called()
        self.capture.assert_not_called()

    def test_original_observation_full_held_join_and_real_key_replay(self):
        with self.call() as value:
            self.assertEqual(set(SDK_FACADE_TARGETS), self.f.f.active)
            self.assertEqual(self.receipt_path.read_bytes(), value["receiptBytes"])
            self.assertEqual(self.receipt, value["receipt"])
            self.assertEqual(canonical_json_bytes(self.f.expected), (value["stage"] / original.OUTPUT_PATH).read_bytes())
            stage = value["stage"]
        self.assertFalse(stage.exists())
        self.assertFalse(self.f.f.active)
        self.capture.assert_called_once()
        self.plan.assert_called_once_with(self.plan.call_args.args[0], self.root,
                                          expected_revision=self.receipt["producer"]["commit"])

    def test_explicit_original_context_and_exact_worker_command(self):
        for field in ("repositoryRoot", "metadataRequest"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "worker differs"):
                with self.call(original_context={**self.context, field: "/wrong/original"}):
                    pass
        def remove_offline(root):
            path = root / "worker/execution.json"
            value = original._json(path)
            value["command"].remove("--offline")
            path.write_bytes(canonical_json_bytes(value))
        self.capture_mutation = remove_offline
        with self.assertRaisesRegex(ValueError, "fixed offline command"), self.call():
            pass

    def test_retained_predecessor_and_zip_substitution_reject_before_yield(self):
        for name in ("zip", "stage", "receipt", "extra"):
            def corrupt(root, mode=name):
                parent = root / "originals/validations/jvm"
                if mode == "zip": (parent / "capture/transport.zip").write_bytes(b"another upload")
                elif mode == "stage": (parent / "stage/extra").write_bytes(b"extra")
                elif mode == "receipt": (parent / "phase-receipt.json").write_bytes(b"{}\n")
                else: (root / "worker/unexpected").write_bytes(b"extra")
            self.capture_mutation = corrupt
            with self.subTest(name=name), self.assertRaises(ValueError), self.call():
                pass

    def test_original_key_and_version_cannot_be_replaced(self):
        self.git_inventory.return_value = [{**self.inventory[0], "sha256": "sha256:" + "e" * 64}]
        with self.assertRaisesRegex(ValueError, "original source/version/phase key"), self.call():
            pass

    def test_lifetime_mutations_and_full_reader_exit_failure_reject(self):
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as value:
            (value["original"] / "worker/gradle.log").write_bytes(b"late mutation")
        with self.assertRaisesRegex(ValueError, "changed"), self.call() as value:
            value["transport"]["observed"].append({"late": True})
        self.f.f.exit_failure = "jvm"
        with self.assertRaisesRegex(ValueError, "reader exit rejected"), self.call():
            pass

    def test_caller_context_mutation_and_unauthorized_history_reject(self):
        before = deepcopy(self.context)
        with self.assertRaisesRegex(ValueError, "changed"), self.call():
            self.context["metadataRequest"] = "/late/request.json"
        self.context = before
        self.plan.return_value["remoteBuildAuthorized"] = False
        with self.assertRaisesRegex(ValueError, "not authorized"), self.call():
            pass

    def test_original_metadata_holds_independent_archives_outside_retained_payload(self):
        archive = self.f.f.archive
        with self.assertRaisesRegex(ValueError, "changed"):
            with self.call() as value:
                self.assertEqual(archive, Path(
                    self.held.call_args.kwargs["validations"]["ios-arm64"]["nativeCompilerArchive"]))
                self.assertNotIn(str(archive), (value["stage"] / original.OUTPUT_PATH).read_text())
                archive.write_bytes(b"caller archive substituted during metadata use")

    def test_real_planner_binds_each_selected_validation_output(self):
        original._replan(self.root, self.receipt, self.validation_receipts)
        changed = deepcopy(self.validation_receipts)
        changed["jvm"]["receipt"]["outputs"][0]["sha256"] = "sha256:" + "1" * 64
        with self.assertRaisesRegex(ValueError, "original source/version/phase key"):
            original._replan(self.root, self.receipt, changed)

    def test_receipt_mutation_during_source_discovery_cannot_replace_initial_bytes(self):
        sources = original._sources
        changed = deepcopy(self.receipt)
        changed["producer"]["runId"] += 1
        def mutate(request):
            result = sources(request)
            self.receipt_path.write_bytes(canonical_json_bytes(changed))
            return result
        with patch.object(original, "_sources", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "inputs, outputs or caller authority changed"), self.call():
                self.fail("A receipt replaced during setup must never reach the caller")
        self.capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()

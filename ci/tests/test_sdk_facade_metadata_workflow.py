"""Real held composition, writer and shard; election/original readers/process mocked."""

from contextlib import contextmanager, redirect_stderr
from copy import deepcopy
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_facade_metadata_workflow as workflow
from ci.tests import test_sdk_facade_metadata_inputs as fixtures
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_sdk_facade_workflow import assert_metadata_cli_context
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, snapshot_regular_tree, sha256_bytes
from products.plan import _upstream_record
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, verify_phase_shard
from products.registry import SDK_FACADE_TARGETS
from products.sdk_platform_metadata import write_facade_metadata_content


class FacadeMetadataWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeMetadataInputsTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.f.root
        self.destination = self.root / "upload"
        self.discovery = self.root / "discovery"
        self.discovery.mkdir()
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "runId": 101, "runAttempt": 2, "pullRequest": 31,
            "workflowPath": ".github/workflows/ci.yml"}
        provisional = self.root / "provisional"
        self.expected = write_facade_metadata_content(self.f.f.request_path, provisional / workflow.OUTPUT_PATH)
        manifest = write_output_manifest(provisional, "sdk", "sdk-core", "metadata", "common", "0.8.7",
                                          {workflow.OUTPUT_KIND: "outputs/evidence"})
        receipt = write_receipt(self.root / "metadata-fixture.json", product="sdk", component="sdk-core",
            phase="metadata", target="common", version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"],
            upstream=[_upstream_record(self.f.f.originals[target]) for target in SDK_FACADE_TARGETS],
            context={"producer": self.producer})
        self.ready = {key: receipt[key] for key in PHASE_PLAN_KEYS}
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        (self.tooling / "fixture.jar").write_bytes(b"opaque tooling; original gates mocked")
        self.key, self.java = self.root / "key.pub", self.root / "java"
        self.key.write_bytes(b"public fixture")
        self.java.write_bytes(b"java fixture")
        self.election = self.enterContext(patch.object(workflow.product_reuse, "_verified_product_state",
            return_value=SimpleNamespace(prior_ready_plans={workflow._INSTANCE: self.ready}, producer=self.producer,
                                         expected_fixed={"versions": {"sdk": "0.8.7"}})))
        self.materialize = self.enterContext(patch.object(workflow.product_reuse, "materialize_product_predecessors",
                                                        side_effect=self.materialize_inputs))
        self.enterContext(patch.object(workflow, "_request_inventory", side_effect=lambda path: {path: workflow.product_reuse.sha256_file(path)}))
        self.held = self.enterContext(patch.object(workflow, "verified_facade_metadata_inputs", side_effect=self.f.call))
        self.enterContext(patch.object(workflow.product_reuse, "_runtime_worker_environment",
            return_value=({}, self.root / "gradlew")))
        self.checkout = self.enterContext(patch.object(workflow.product_reuse, "_runtime_worker_checkout"))
        self.process = self.enterContext(patch.object(workflow.subprocess, "run", side_effect=self.produce))
        finalizer = workflow.product_reuse.finalize_phase_object
        def finalize(**kwargs):
            self.assertFalse(self.f.active)
            return finalizer(**kwargs)
        self.finalize = self.enterContext(patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=finalize))

    def materialize_inputs(self, plan, discovery, state, instance, destination, **kwargs):
        self.assertEqual(workflow._INSTANCE, instance)
        self.assertEqual(self.ready["buildKey"], kwargs["expected_build_key"])
        self.assertEqual(17, len(kwargs["materialized_scope"]))
        self.assertFalse(any(item.product == "runtime" for item in kwargs["materialized_scope"]))
        self.assertEqual(set(SDK_FACADE_TARGETS), {item.target for item in kwargs["materialized_scope"]
            if item.product == "sdk" and item.phase == "validation"})
        destination.mkdir()
        for target in ("package", *SDK_FACADE_TARGETS):
            name = "sdk-sdk-core-package-common" if target == "package" else f"sdk-sdk-core-validation-{target}"
            snapshot_regular_tree(self.f.f.stages[target], destination / name / "stage")
            (destination / name / "phase-receipt.json").write_bytes(self.f.f.receipts[target].read_bytes())
        (destination / "phase-plan.json").write_bytes(canonical_json_bytes(self.ready))
        (destination / "producer.json").write_bytes(canonical_json_bytes(self.producer))
        return deepcopy(self.ready)

    def produce(self, command, **kwargs):
        self.assertEqual(getattr(self, "expected_active_readers", 11), len(self.f.active))
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertIn("--offline", command)
        self.assertEqual(1, command.count("ciProductPhase"))
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        self.assertEqual("metadata", fields["codexAgent.phase"])
        self.assertEqual("common", fields["codexAgent.target"])
        stage = self.root / "build/product-stage/sdk/sdk-core/metadata/common"
        write_facade_metadata_content(Path(fields["codexAgent.sdkFacadeMetadataRequest"]), stage / workflow.OUTPUT_PATH)
        write_output_manifest(stage, "sdk", "sdk-core", "metadata", "common", "0.8.7",
                              {workflow.OUTPUT_KIND: "outputs/evidence"})
        return SimpleNamespace(returncode=0)

    def arguments(self):
        return dict(plan=self.f.plan, discovery=self.discovery, state=self.discovery, destination=self.destination,
            expected_build_key=self.ready["buildKey"], validations=self.f.records,
            contract_digest=self.f.f.request["contractDigest"], component_digests=self.f.f.request["componentDigests"],
            repository_root=self.root, environ={}, token="explicit-caller-token", trusted_workflow_sha="f" * 40,
            tooling_evidence=self.tooling, tooling_public_key=self.key, java_executable=self.java,
            policy_revision="e" * 40, required_trust_domain="development")

    def test_fixed_producer_retains_exact_original_references_and_finalizes_after_contexts_close(self):
        result = workflow.execute(**self.arguments())
        self.assertEqual("f" * 40, self.election.call_args.kwargs["sdk_original_workflow_sha"])
        self.assertEqual("f" * 40, self.materialize.call_args.kwargs["sdk_original_workflow_sha"])
        self.assertEqual(canonical_json_bytes(self.expected), result["content"].read_bytes())
        self.assertEqual(result["shard"], verify_phase_shard(self.destination / "shard", workflow._INSTANCE))
        self.assertEqual(str(self.root), result["originalContext"]["repositoryRoot"])
        request = Path(result["originalContext"]["metadataRequest"])
        self.assertEqual("metadata-request.json", request.name)
        self.assertFalse(request.exists())  # The caller preserves the path, not a mutable private input.
        self.assertEqual({"inputs", "selection", "worker", "originals", "shard"},
                         {path.name for path in self.destination.iterdir()})
        for index, target in enumerate(SDK_FACADE_TARGETS):
            original = self.destination / "originals/validations" / target
            self.assertEqual(self.f.f.receipts[target].read_bytes(), (original / "phase-receipt.json").read_bytes())
            self.assertEqual({"stage", "phase-receipt.json", "original-reference.json"},
                             {p.name for p in original.iterdir()})
            reference = load_canonical_json_bytes((original / "original-reference.json").read_bytes())
            self.assertEqual(sha256_bytes(self.f.f.receipts[target].read_bytes()), reference["receiptSha256"])
            self.assertEqual({"id": index + 1, "bytes": len(b"opaque original ZIP; official gate mocked"),
                "sha256": sha256_bytes(b"opaque original ZIP; official gate mocked")}, reference["artifact"])
            self.assertFalse((original / "capture").exists())
        self.finalize.assert_called_once()
        self.assertFalse(self.f.active)
        self.assertEqual(b"", (result["diagnostics"] / "gradle.log").read_bytes())
        for call in (self.election.call_args, self.materialize.call_args):
            for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                self.assertNotIn(name, call.kwargs)

    def test_qualified_holder_through_worker_never_acquires_or_replays_old_archives(self):
        from ci import sdk_facade_original_inputs as holder
        from ci.products.sdk_facade_metadata_admission import fresh_metadata_arguments
        self.expected_active_readers = 0
        with self.f.qualified(self.producer) as q:
            q.elected.prior_ready_plans = {workflow._INSTANCE: self.ready}
            q.elected.producer = self.producer
            q.elected.expected_fixed = {"versions": {"sdk": "0.8.7"}}
            self.election.return_value = q.elected
            args = self.arguments()
            policy = {"plan": str(args["plan"]), "toolingEvidence": str(self.tooling),
                "toolingPublicKey": str(self.key), "javaExecutable": str(self.java),
                "toolingKeyring": None, "toolingKeysDirectory": None, "toolingTrustDomain": "development",
                "contractDigest": args["contract_digest"], "componentDigests": args["component_digests"],
                "validations": {t: {k: str(v) for k, v in record.items()
                    if k not in {"artifactId", "artifactSha256"}} for t, record in self.f.records.items()}}
            with patch.object(holder, "_request_paths", side_effect=lambda path: {path}), \
                    patch.object(holder.product_reuse, "_verified_product_state", return_value=q.elected), \
                    patch.object(holder.product_reuse, "materialize_product_predecessors", side_effect=self.materialize_inputs), \
                    patch.object(holder, "locate_original_facade_upload", side_effect=AssertionError("old lookup")), \
                    patch.object(holder, "capture_sdk_facade_validation_upload", side_effect=AssertionError("old archive")):
                with holder.held_captured_facade_metadata_policy(args["plan"], self.discovery, self.discovery,
                        expected_build_key=self.ready["buildKey"], replay_policy=policy, completed_frozen=q.cap,
                        repository_root=self.root, environ={}, token=args["token"],
                        trusted_workflow_sha=args["trusted_workflow_sha"]) as descriptor:
                    value = load_canonical_json_bytes(descriptor.read_bytes())
                    self.assertEqual([], value["records"])
                    self.assertEqual([], list(Path(value["evidenceRoot"]).iterdir()))
                    parsed = fresh_metadata_arguments(value["policy"])
                    result = workflow.execute(**{**args, **parsed, "completed_frozen": q.cap})
            self.assertEqual(canonical_json_bytes(self.expected), result["content"].read_bytes())
            self.f.reader.assert_not_called()
            self.f.retained_reader.assert_not_called()
            self.assertEqual(23, q.observed.call_count)  # Holder11 + worker package/all11.
            for target in SDK_FACADE_TARGETS:
                self.assertFalse((self.destination / "originals/validations" / target / "capture").exists())
            self.process.assert_called_once()
            self.finalize.assert_called_once()

    def test_native_archive_mutation_in_qualified_worker_prevents_finalization(self):
        self.expected_active_readers = 0
        with self.f.qualified(self.producer) as q:
            q.elected.prior_ready_plans = {workflow._INSTANCE: self.ready}
            q.elected.producer = self.producer
            q.elected.expected_fixed = {"versions": {"sdk": "0.8.7"}}
            self.election.return_value = q.elected
            def produce(*args, **kwargs):
                result = self.produce(*args, **kwargs)
                stamp = self.f.archive.stat()
                raw = self.f.archive.read_bytes()
                self.f.archive.write_bytes(b"X" + raw[1:])
                os.utime(self.f.archive, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                return result
            self.process.side_effect = produce
            with self.assertRaises(ValueError):
                workflow.execute(**self.arguments(), completed_frozen=q.cap)
            self.process.assert_called_once()
            self.finalize.assert_not_called()
            self.assertFalse((self.destination / "shard").exists())

    def test_metadata_admission_objects_forward_to_both_state_replays_only(self):
        admissions = {"sdk_facade_metadata_admission": object(), "sdk_android_metadata_admission": object()}
        workflow.execute(**self.arguments(), **admissions)
        for name, value in admissions.items():
            for call in (self.election.call_args, self.materialize.call_args):
                self.assertIs(value, call.kwargs[name])
            self.assertNotIn(name, self.held.call_args.kwargs)
            self.assertNotIn(name, self.process.call_args.kwargs)
            for path in self.destination.rglob("*"):
                if path.is_file():
                    self.assertNotIn(name.encode(), path.read_bytes(), str(path))

    def test_unelected_or_wrong_materialized_package_never_runs_producer(self):
        with self.assertRaisesRegex(ValueError, "not ready"):
            workflow.execute(**{**self.arguments(), "expected_build_key": "sha256:" + "e" * 64})
        def wrong(*args, **kwargs):
            result = self.materialize_inputs(*args, **kwargs)
            (args[4] / "sdk-sdk-core-package-common/phase-receipt.json").write_bytes(b"{}\n")
            return result
        self.materialize.side_effect = wrong
        with self.assertRaisesRegex(ValueError, "original package differs"):
            workflow.execute(**self.arguments())
        self.process.assert_not_called()
        self.finalize.assert_not_called()

    def test_context_exit_failure_or_late_input_mutation_cannot_finalize(self):
        self.f.exit_failure = "jvm"
        with self.assertRaisesRegex(ValueError, "reader exit rejected"):
            workflow.execute(**self.arguments())
        self.finalize.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_native_archive_mutation_after_last_reader_exit_blocks_publication(self):
        def mutate(target):
            if not self.f.active:
                self.f.archive.write_bytes(b"caller archive changed at final original exit")
        self.f.exit_callback = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            workflow.execute(**self.arguments())
        self.finalize.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())

    def test_process_failure_retains_diagnostics_without_receipt(self):
        self.process.side_effect = lambda *args, **kwargs: SimpleNamespace(returncode=23)
        with self.assertRaisesRegex(ValueError, "exit code 23"):
            workflow.execute(**self.arguments())
        evidence = load_canonical_json_bytes((self.destination / "worker/execution.json").read_bytes())
        self.assertEqual(23, evidence["returnCode"])
        self.finalize.assert_not_called()

    def test_late_retained_or_tool_mutation_is_rejected(self):
        def mutate(*args, **kwargs):
            result = self.produce(*args, **kwargs)
            self.java.write_bytes(b"changed Java after process")
            return result
        self.process.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed"):
            workflow.execute(**self.arguments())
        self.finalize.assert_not_called()

    def test_added_compatibility_inventory_entry_is_rechecked(self):
        expanded = False
        def inventory(path):
            records = {path: workflow.product_reuse.sha256_file(path)}
            if expanded:
                records[self.java] = workflow.product_reuse.sha256_file(self.java)
            return records
        def mutate(*args, **kwargs):
            nonlocal expanded
            result = self.produce(*args, **kwargs)
            expanded = True
            return result
        self.process.side_effect = mutate
        with patch.object(workflow, "_request_inventory", side_effect=inventory):
            with self.assertRaisesRegex(ValueError, "changed"):
                workflow.execute(**self.arguments())
        self.finalize.assert_not_called()

    def test_retained_validation_stage_must_equal_source_before_finalization(self):
        snapshot = workflow.snapshot_regular_tree
        def changed(source, destination, **kwargs):
            result = snapshot(source, destination, **kwargs)
            if destination.name == "stage" and destination.parent.parent.name == "validations":
                (destination / "unexpected-file").write_bytes(b"different retained copy")
            return result
        with patch.object(workflow, "snapshot_regular_tree", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during retention"):
                workflow.execute(**self.arguments())
        self.process.assert_not_called()
        self.finalize.assert_not_called()

    def test_reference_write_mismatch_cannot_finalize(self):
        write = workflow.write_canonical_json
        def changed(path, value):
            result = write(path, value)
            if path.name == "original-reference.json":
                path.write_bytes(b"{}\n")
            return result
        with patch.object(workflow, "write_canonical_json", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "reference changed during retention"):
                workflow.execute(**self.arguments())
        self.process.assert_not_called()
        self.finalize.assert_not_called()

    def test_context_exit_diagnostics_mutation_cannot_finalize(self):
        @contextmanager
        def held(**kwargs):
            with self.f.call(**kwargs) as value:
                yield value
            (self.destination / "worker/gradle.log").write_bytes(b"changed at context exit")
        self.held.side_effect = held
        with self.assertRaisesRegex(ValueError, "changed"):
            workflow.execute(**self.arguments())
        self.finalize.assert_not_called()

    def test_strict_cli_reads_canonical_controls_and_uses_token_only_from_environment(self):
        validations = self.root / "validation-controls.json"
        validations.write_bytes(canonical_json_bytes({target: {key: str(value) if isinstance(value, Path) else value
            for key, value in record.items()} for target, record in self.f.records.items()}))
        components = self.root / "components.json"
        components.write_bytes(canonical_json_bytes(self.f.f.request["componentDigests"]))
        arguments = {**self.arguments(), "validations": validations, "component_digests": components}
        argv = [item for key, value in arguments.items() if key not in {"environ", "token"}
                for item in ("--" + key.replace("_", "-") + ("-root" if key in {"discovery", "state"} else ""), str(value))]
        assert_metadata_cli_context(self, workflow, argv)
        with patch.object(workflow, "execute") as execute, patch.dict(os.environ, {"GITHUB_TOKEN": "cli-token"}):
            self.assertEqual(0, workflow.main(argv))
            self.assertEqual("cli-token", execute.call_args.kwargs["token"])
            for name in ("sdk_facade_metadata_admission", "sdk_android_metadata_admission"):
                self.assertNotIn(name, execute.call_args.kwargs)
            self.assertEqual(self.f.f.request["componentDigests"], execute.call_args.kwargs["component_digests"])
            self.assertEqual(str(self.f.archive),
                execute.call_args.kwargs["validations"]["ios-arm64"]["nativeCompilerArchive"])
            for extra in (["--token", "not-allowed"], ["--tooling-keyring", str(self.key)], ["--unknown"],
                          ["--sdk-facade-metadata-admission", "transport.json"],
                          ["--sdk-android-metadata-admission", "transport.json"]):
                with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    workflow.main(argv + extra)

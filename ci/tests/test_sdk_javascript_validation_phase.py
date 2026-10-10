"""Original validation boundaries; simulated tooling is not parity acceptance."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.sdk_javascript_validation_phase import (
    VerifiedJavaScriptValidationProjection, verify_sdk_javascript_validation_phase,
    verify_sdk_javascript_validation_projection,
)
from ci.tests import test_sdk_javascript_metadata_admission as admission_fixture


class JavaScriptValidationPhaseTest(unittest.TestCase):
    def setUp(self):
        fixture = admission_fixture.SdkJavaScriptMetadataAdmissionTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        support = fixture.support
        self.arguments = {name: support.args[name] for name in (
            "repository", "contract_stage", "contract_receipt", "package_stage", "package_receipt",
            "validation_stage", "validation_receipt", "runtime_validation_stage",
            "runtime_validation_receipt", "original_consumer_directory", "tooling_evidence",
            "tooling_public_key", "java_executable", "policy_revision", "required_trust_domain",
        )}
        self.arguments["tooling_keyring"] = None
        self.arguments["tooling_keys_directory"] = None
        self.replay_bytes = support.content
        self.calls = []

    @contextmanager
    def tooling(self, evidence, repository, public_key, **kwargs):
        self.assertEqual((evidence, repository, public_key), (
            self.arguments["tooling_evidence"], self.arguments["repository"],
            self.arguments["tooling_public_key"]))
        self.assertEqual(kwargs["policy_revision"], self.arguments["policy_revision"])
        yield self.fixture.support.jar

    def process(self, command, **kwargs):
        if command[0] == "git":
            return admission_fixture._RUN(command, **kwargs)
        self.assertEqual(command[:4], [str(self.arguments["java_executable"]), "-jar",
            str(self.fixture.support.jar), "write-javascript-metadata-content"])
        fields = dict(zip(command[4::2], command[5::2]))
        self.calls.append(fields)
        self.assertEqual(fields["--original-consumer-directory"], str(self.arguments["original_consumer_directory"]))
        self.assertEqual(fields["--runtime-version"], "0.2.7")
        self.assertTrue(kwargs["check"])
        self.assertEqual((kwargs["stdout"], kwargs["stderr"]), (subprocess.PIPE, subprocess.PIPE))
        self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
        Path(fields["--content-output"]).write_bytes(self.replay_bytes)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    def verify(self, *, operation=verify_sdk_javascript_validation_phase, **overrides):
        with patch("ci.products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("ci.products.sdk_javascript_validation_phase.subprocess.run", self.process):
            return operation(**(self.arguments | overrides))

    def test_projection_binds_exact_original_raw_inventory_without_rewriting_it(self):
        stage = self.arguments["validation_stage"]
        before = regular_file_inventory(stage)
        proof = self.verify(operation=verify_sdk_javascript_validation_projection)
        receipt, raw = self.verify()
        view = proof.output_inventory(sha256_bytes(raw), receipt["outputs"], identity=receipt)
        self.assertEqual(view[0]["sha256"], sha256_bytes(self.replay_bytes))
        self.assertEqual(proof.upstream_record(receipt)["buildKey"], receipt["buildKey"])
        self.assertEqual(before, regular_file_inventory(stage))
        with self.assertRaisesRegex(TypeError, "authenticated full matcher"):
            VerifiedJavaScriptValidationProjection(raw, self.replay_bytes, object())
        for digest, outputs, identity in (
            ("sha256:" + "0" * 64, receipt["outputs"], receipt),
            (sha256_bytes(raw), [], receipt),
            (sha256_bytes(raw), receipt["outputs"], {**receipt, "target": "other"}),
        ):
            with self.assertRaisesRegex(ValueError, "original receipt"):
                proof.output_inventory(digest, outputs, identity=identity)

    def test_projection_compares_verified_content_not_raw_paths_or_timings(self):
        original = self.verify(operation=verify_sdk_javascript_validation_projection)
        receipt = self.fixture.support.receipts["validation"]
        original_record = original.upstream_record(receipt)
        stage = self.arguments["validation_stage"]
        (stage / "outputs/execution/typescript-execution.json").write_bytes(
            canonical_json_bytes({"command": ["/different/node", "/different/tsc"], "elapsedNs": 123}))
        (stage / "outputs/test-report/packed-tests.xml").write_bytes(b'<testsuites time="9.9"/>\n')
        self.fixture.replan("validation", self.fixture.validation_commit, self.fixture.validation_tree)
        changed = self.verify(operation=verify_sdk_javascript_validation_projection)
        receipt = self.fixture.support.receipts["validation"]
        self.assertEqual(original_record, changed.upstream_record(receipt))
        with self.assertRaisesRegex(ValueError, "original receipt"):
            original.upstream_record(receipt)
        # The mocked matcher boundary is not acceptance evidence. Distinct
        # authenticated semantic results must still produce distinct views.
        for change in ("package", "api", "test-program", "scenario"):
            self.replay_bytes = canonical_json_bytes({"verified-content-change": change})
            (stage / "outputs/binding-evidence/javascript-typescript-parity.json").write_bytes(self.replay_bytes)
            self.fixture.replan("validation", self.fixture.validation_commit, self.fixture.validation_tree)
            proof = self.verify(operation=verify_sdk_javascript_validation_projection)
            self.assertNotEqual(original_record["outputsDigest"], proof.upstream_record(
                self.fixture.support.receipts["validation"])["outputsDigest"])

    def test_metadata_reuse_waits_for_caller_proof_then_preserves_originals(self):
        from ci.products.registry import PhaseInstanceId
        from ci.products.plan import plan_phase
        from ci.tests import test_product_reuse as reuse_fixture

        metadata = PhaseInstanceId("sdk", "javascript", "metadata", "node")
        validation = PhaseInstanceId("sdk", "javascript", "validation", "node")
        support = reuse_fixture.ProductReuseTest()
        support.root = self.fixture.root / "reuse-control"
        support.root.mkdir()
        repository, revision, _ = support.runtime_flags_revision()
        proofs = {}

        def proof(envelope):
            digest = envelope["receiptSha256"]
            if digest not in proofs:
                with patch("ci.products.sdk_javascript_validation_phase._verify_sdk_javascript_validation",
                           return_value=(envelope["receipt"], envelope["receiptBytes"], self.replay_bytes)):
                    proofs[digest] = verify_sdk_javascript_validation_projection()
            return proofs[digest]

        original_plan = reuse_fixture.plan_for

        def fixture_plan(instance, inputs, resolved):
            if instance == metadata:
                return plan_phase(instance, upstream_receipts=[resolved[validation]["receipt"]],
                                  sdk_javascript_validation_projection=proof(resolved[validation]), **inputs[instance])
            return original_plan(instance, inputs, resolved)

        with patch.object(reuse_fixture, "plan_for", fixture_plan):
            inputs, retained = reuse_fixture.retained_product_closure(metadata,
                repository_root=repository, repository_revision=revision)
        options = dict(repository_root=repository, repository_revision=revision,
                       runtime_validation_projection_provider=reuse_fixture.test_runtime_projection_provider)
        waiting, _ = reuse_fixture.advance_reuse([metadata], inputs, list(retained.values()), support.session(), **options)
        self.assertTrue(all(not matrix for matrix in waiting["matrices"].values()))
        self.assertEqual("sdk-javascript-validation-evidence", waiting["continuationRequirements"][0]["kind"])

        def provider(instance, originals):
            self.assertEqual(instance, metadata)
            self.assertEqual(len(originals), 4)
            self.assertEqual(originals[2], retained[validation])
            return proof(originals[2])

        complete, originals = reuse_fixture.advance_reuse([metadata], inputs, list(retained.values()), support.session(),
            **options, sdk_javascript_validation_projection_provider=provider)
        self.assertTrue(complete["fullReuse"])
        self.assertTrue(all(not matrix for matrix in complete["matrices"].values()))
        self.assertEqual({value["receiptSha256"] for value in retained.values()},
                         {value["receiptSha256"] for value in originals})
        forged = {identity: dict(values) for identity, values in inputs.items()}
        forged[metadata]["sdk_javascript_validation_projection"] = proof(retained[validation])
        with self.assertRaisesRegex(ValueError, "Callers cannot supply"):
            reuse_fixture.advance_reuse([metadata], forged, [], support.session(), **options)

    def test_controller_authenticates_original_upload_before_selecting_original_source_policy(self):
        from ci.tests.test_runtime_resumed_phase import adapter
        from products.restore import store_local_object

        support = self.fixture.support
        validation = support.receipts["validation"]
        validation["producer"].update(event="pull_request", workflowPath=".github/workflows/ci.yml",
            runId=123, runAttempt=1, pullRequest=31)
        support.receipt_paths["validation"].write_bytes(canonical_json_bytes(validation))
        originals, records = [], []
        for name in ("contract", "package", "validation", "runtime"):
            receipt = support.receipts[name]
            stored = store_local_object(support.stage_paths[name], support.receipt_paths[name], support.root / "objects")
            originals.append({"receipt": receipt, "receiptBytes": support.receipt_paths[name].read_bytes(),
                              "receiptSha256": stored["receiptSha256"], "objectSha256": stored["objectSha256"]})
            records.append({**{field: receipt[field] for field in ("product", "component", "phase", "target", "buildKey")},
                "receiptSha256": stored["receiptSha256"], "objectSha256": stored["objectSha256"],
                "objectPath": stored["path"].relative_to(support.root).as_posix()})
        metadata = adapter.PhaseInstanceId("sdk", "javascript", "metadata", "node")
        request = {"requested": [adapter._identity_record(metadata)], "availableObjects": records,
                   "artifactRoot": str(support.root), "repositoryRevision": self.fixture.metadata_commit}
        policy = {"evidence": str(self.arguments["tooling_evidence"]), "publicKey": str(self.arguments["tooling_public_key"]),
                  "javaExecutable": str(self.arguments["java_executable"]), "requiredTrustDomain": "development",
                  "keyring": None, "keysDirectory": None}
        context = {"plan_path": support.root / "caller-plan.json", "repository_root": self.arguments["repository"],
                   "trusted_workflow_sha": "c" * 40, "token": "fixture-observation", "environ": {}}
        calls = []

        def capture(*args, **kwargs):
            self.assertEqual(args[0], context["plan_path"])
            self.assertEqual(kwargs["trusted_workflow_sha"], context["trusted_workflow_sha"])
            self.assertEqual(Path(kwargs["validation_receipt_path"]).read_bytes(), originals[2]["receiptBytes"])
            calls.append("authenticated-original-upload")
            return {"originalConsumerDirectory": str(self.arguments["original_consumer_directory"])}

        self.arguments["policy_revision"] = self.fixture.validation_commit
        with patch("sdk_javascript_validation_locator.locate_javascript_validation_upload",
                   return_value={"artifact_id": 17, "artifact_sha256": "sha256:" + "a" * 64}), \
                patch.object(adapter, "capture_sdk_javascript_validation_upload", capture), \
                patch("products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("products.sdk_javascript_validation_phase.subprocess.run", self.process):
            provider = adapter._javascript_projection_provider(request, policy, context)
            proof = provider(metadata, tuple(originals))
        self.assertEqual(calls, ["authenticated-original-upload"])
        self.assertEqual(proof.policy_revision, self.fixture.validation_commit)
        self.assertNotEqual(proof.policy_revision, request["repositoryRevision"])
        self.assertEqual(proof.content_bytes(validation), self.replay_bytes)

    def test_original_git_plan_runtime_predecessor_and_complete_replay(self):
        receipt, raw = self.verify()
        self.assertEqual(raw, self.arguments["validation_receipt"].read_bytes())
        self.assertEqual(receipt["producer"]["commit"], self.fixture.validation_commit)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["--contract-version"], "0.2.0")
        self.assertEqual(self.calls[0]["--sdk-version"], "0.3.0")

    def test_wrong_runtime_receipt_rejected_before_matcher(self):
        runtime = self.arguments["runtime_validation_receipt"]
        changed = self.fixture.support.receipts["runtime"].copy()
        changed["outputs"] = [dict(record) for record in changed["outputs"]]
        changed["outputs"][0]["sha256"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "runtime.json"
            path.write_bytes(canonical_json_bytes(changed))
            with self.assertRaisesRegex(ValueError, "original producer plan"):
                self.verify(runtime_validation_receipt=path)
        self.assertFalse(self.calls)

    def test_original_consumer_source_and_replayed_behavior_must_match(self):
        program = self.arguments["validation_stage"] / "outputs/test-program/smoke.cjs"
        original = program.read_bytes()
        try:
            program.write_bytes(b"changed consumer program\n")
            with self.assertRaisesRegex(ValueError, "original Git source"):
                self.verify()
            self.assertFalse(self.calls)
        finally:
            program.write_bytes(original)
        self.replay_bytes = b'{"different":"behavior"}\n'
        with self.assertRaisesRegex(ValueError, "full authenticated replay"):
            self.verify()


if __name__ == "__main__":
    unittest.main()

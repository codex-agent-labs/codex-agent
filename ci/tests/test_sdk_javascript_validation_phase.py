"""Original validation boundaries; simulated tooling is not parity acceptance."""

from contextlib import contextmanager
import copy
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

    def test_receipt_consistency_requires_both_exact_javascript_proofs(self):
        from ci.products.sdk_campaign_index import verify_build_key_output_consistency

        original = copy.deepcopy(self.fixture.support.receipts["validation"])
        original_bytes = canonical_json_bytes(original)
        proof = self.verify(operation=verify_sdk_javascript_validation_projection)
        stage = self.arguments["validation_stage"]
        (stage / "outputs/test-report/packed-tests.xml").write_bytes(b'<testsuites time="9.9"/>\n')
        self.fixture.replan("validation", self.fixture.validation_commit, self.fixture.validation_tree)
        changed = copy.deepcopy(self.fixture.support.receipts["validation"])
        changed_bytes = canonical_json_bytes(changed)
        changed_proof = self.verify(operation=verify_sdk_javascript_validation_projection)
        proofs = {sha256_bytes(original_bytes): proof, sha256_bytes(changed_bytes): changed_proof}
        calls = []

        def provider(receipt):
            digest = sha256_bytes(canonical_json_bytes(receipt))
            calls.append(digest)
            return proofs[digest]

        self.assertEqual(original["buildKey"], changed["buildKey"])
        verify_build_key_output_consistency([original, copy.deepcopy(original)],
            sdk_javascript_validation_projection=provider)
        self.assertEqual(calls, [])  # Unchanged raw inventories need no expensive matcher.
        with self.assertRaisesRegex(ValueError, "conflicting output inventories"):
            verify_build_key_output_consistency([original, changed])
        verify_build_key_output_consistency([original, changed],
            sdk_javascript_validation_projection=provider)
        self.assertEqual(calls, [sha256_bytes(original_bytes), sha256_bytes(changed_bytes)])
        self.assertEqual((canonical_json_bytes(original), canonical_json_bytes(changed)),
                         (original_bytes, changed_bytes))
        for invalid in (lambda _: object(), lambda _: proof):
            with self.assertRaisesRegex(ValueError, "projection is required|original receipt"):
                verify_build_key_output_consistency([original, changed],
                    sdk_javascript_validation_projection=invalid)

        # This fixture simulates the full matcher, not genuine parity acceptance.
        # Different verified content must still fail the consistency gate.
        self.replay_bytes = canonical_json_bytes({"verified-content-change": "scenario"})
        (stage / "outputs/binding-evidence/javascript-typescript-parity.json").write_bytes(self.replay_bytes)
        self.fixture.replan("validation", self.fixture.validation_commit, self.fixture.validation_tree)
        different = self.fixture.support.receipts["validation"]
        different_proof = self.verify(operation=verify_sdk_javascript_validation_projection)
        with self.assertRaisesRegex(ValueError, "conflicting output inventories"):
            verify_build_key_output_consistency([original, different],
                sdk_javascript_validation_projection=lambda r: proof if r == original else different_proof)

    def test_signed_catalog_comparison_preserves_originals_and_reuses_exact_proofs(self):
        from dataclasses import replace
        from ci.products import sdk_campaign_index as index_comparison
        from ci.products.inventory import load_canonical_json_bytes
        from ci.products.restore import store_local_object
        from ci.products.signatures import generate_development_key
        from ci.tests.test_product_reuse import ProductReuseTest, REPOSITORY

        # Existing simulated full-matcher fixture; signing/object checks are real.
        support = self.fixture.support
        support.context["producer"].update(repository=REPOSITORY, event="pull_request",
            workflowPath=".github/workflows/ci.yml", runId=7, runAttempt=1, pullRequest=31)
        catalogs = ProductReuseTest()
        catalogs.root, catalogs.counter = support.root / "catalogs", 0
        catalogs.root.mkdir()
        catalogs.private_key, catalogs.public_key, catalogs.development_signing = \
            generate_development_key(support.root / "catalog-keys")
        originals, proofs, signed = [], {}, []
        for generation in range(2):
            if generation:
                (self.arguments["validation_stage"] / "outputs/test-report/packed-tests.xml").write_bytes(
                    b'<testsuites time="9.9"/>\n')
                support.context["producer"]["runId"] = 8
            self.fixture.replan("validation", self.fixture.validation_commit, self.fixture.validation_tree)
            raw = support.receipt_paths["validation"].read_bytes()
            stored = store_local_object(support.stage_paths["validation"], support.receipt_paths["validation"],
                                        support.root / "catalog-objects")
            envelope = dict(receipt=load_canonical_json_bytes(raw), receiptBytes=raw,
                receiptSha256=stored["receiptSha256"], objectSha256=stored["objectSha256"])
            originals.append(envelope)
            proofs[envelope["receiptSha256"]] = self.verify(operation=verify_sdk_javascript_validation_projection)
            signed.append(catalogs.catalog("same-pr", [(envelope, stored["path"])]))
        before = [source.manifest.read_bytes() for source in signed]
        indexes = [load_canonical_json_bytes(raw) for raw in before]
        self.assertEqual(originals[0]["receipt"]["buildKey"], originals[1]["receipt"]["buildKey"])
        self.assertNotEqual(originals[0]["receipt"]["producer"], originals[1]["receipt"]["producer"])
        calls = []

        def provider(entry, archive):
            calls.append(entry["receiptSha256"])
            self.assertTrue(archive.is_file())
            return proofs[entry["receiptSha256"]]

        with self.assertRaisesRegex(ValueError, "authenticated original evidence"):
            catalogs.session(same_pr=signed)
        session = catalogs.session(same_pr=signed, sdk_javascript_index_projection=provider)
        self.assertEqual(calls, [o["receiptSha256"] for o in originals])
        # Repeating consistency checks uses session proof custody, not another matcher.
        index_comparison.verify_immutable_product_indexes(*indexes,
            sdk_validation_projection=session._catalog_sdk_projection)
        self.assertEqual(len(calls), 2)
        self.assertEqual(before, [source.manifest.read_bytes() for source in signed])
        for envelope in originals:
            self.assertEqual(canonical_json_bytes(envelope["receipt"]), envelope["receiptBytes"])
        with self.assertRaisesRegex(ValueError, "both authenticated objects"):
            catalogs.session(same_pr=[signed[0], replace(signed[1], objects={})],
                sdk_javascript_index_projection=provider)
        with self.assertRaisesRegex(ValueError, "original receipt"):
            catalogs.session(same_pr=signed,
                sdk_javascript_index_projection=lambda *_: proofs[originals[0]["receiptSha256"]])
        self.replay_bytes = canonical_json_bytes({"verified-content-change": "scenario"})
        (support.stage_paths["validation"] / "outputs/binding-evidence/javascript-typescript-parity.json").write_bytes(
            self.replay_bytes)
        self.fixture.replan("validation", self.fixture.validation_commit, self.fixture.validation_tree)
        raw = support.receipt_paths["validation"].read_bytes()
        stored = store_local_object(support.stage_paths["validation"], support.receipt_paths["validation"],
                                    support.root / "catalog-objects")
        changed = dict(receipt=load_canonical_json_bytes(raw), receiptBytes=raw,
            receiptSha256=stored["receiptSha256"], objectSha256=stored["objectSha256"])
        proofs[changed["receiptSha256"]] = self.verify(operation=verify_sdk_javascript_validation_projection)
        different = catalogs.catalog("same-pr", [(changed, stored["path"])])
        with self.assertRaisesRegex(ValueError, "conflict"):
            catalogs.session(same_pr=[signed[0], different], sdk_javascript_index_projection=provider)

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

    def test_controller_authenticates_original_upload_with_current_verifier_and_original_sources(self):
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

        self.arguments["policy_revision"] = self.fixture.metadata_commit
        with patch("sdk_javascript_validation_locator.locate_javascript_validation_upload",
                   return_value={"artifact_id": 17, "artifact_sha256": "sha256:" + "a" * 64}), \
                patch.object(adapter, "capture_sdk_javascript_validation_upload", capture), \
                patch("products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("products.sdk_javascript_validation_phase.subprocess.run", self.process):
            cache = {}
            provider = adapter._javascript_projection_provider(request, policy, context, _proofs=cache)
            proof = provider(metadata, tuple(originals))
            from ci.tests.test_product_reuse import ProductReuseTest
            entry = ProductReuseTest.entry(originals[2])
            indexes = adapter._javascript_index_projection_provider(request, policy, context, _proofs=cache)
            archive = support.root / records[2]["objectPath"]
            self.assertIs(proof, indexes(entry, archive))
            missing = adapter._javascript_index_projection_provider(
                {**request, "availableObjects": records[1:]}, policy, context)
            with self.assertRaisesRegex(ValueError, "original dependency evidence"):
                missing(entry, archive)
            # Independent catalog invocation follows the same real source/plan/
            # transport matcher boundary, not an alias or native-proof factory.
            independent = adapter._javascript_index_projection_provider(request, policy, context)
            self.assertEqual(independent(entry, archive).content_bytes(validation), self.replay_bytes)
        self.assertEqual(calls, ["authenticated-original-upload", "authenticated-original-upload"])
        self.assertEqual(proof.policy_revision, request["repositoryRevision"])
        self.assertNotEqual(proof.policy_revision, validation["producer"]["commit"])
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

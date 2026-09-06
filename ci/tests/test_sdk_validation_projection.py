"""Proof orchestration negatives; mocked tooling is never full matcher/host evidence."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.sdk_validation import (
    VerifiedSdkValidationProjection, verify_sdk_validation_projection, sdk_validation_provider,
    decode_sdk_validation_records, rebase_sdk_validation_records, _EVIDENCE_PATHS,
)
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.selection import classify_paths, phase_inventory_paths
from ci.products.aggregate import verified_index_content, verify_immutable_product_indexes
from ci.products.index import (
    IndexEntrySource, SignedProductIndex, build_product_index, verify_sdk_validation_index_object,
    verify_signed_product_index, write_signed_product_index,
)
from ci.products.plan import verify_build_key_output_consistency, plan_phase, _sdk_validation_projections_from_request
from ci.products.restore import store_local_object
from ci.products.reuse import LookupSession, RemoteCatalog
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.product_chain_support import write_receipt


class SdkValidationProjectionTest(unittest.TestCase):
    def test_admission_control_replans_without_changing_payload_keys(self):
        path = "ci/products/sdk_validation.py"
        self.assertEqual(set(PHASE_INSTANCE_IDS), set(classify_paths((path,)).instances))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths((path,), instance))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-proof-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic trusted Java, never executed")
        self.context = {"producer": {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local", "runId": None,
            "runAttempt": None, "pullRequest": None}}
        self.args = dict(repository=self.root, component="python", target="linux-x64",
            compatibility_request=self.root / "request.json", runtime_stages=self.root / "runtime",
            staged_sdks=self.root / "sdks", tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "public.pub", java_executable=self.java,
            policy_revision="a" * 40, required_trust_domain="development")
        for phase, target in (("package", "desktop"), ("validation", "linux-x64")):
            stage = self.root / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/original.txt").write_bytes(f"original {phase} evidence\n".encode())
            manifest = write_output_manifest(stage, "sdk", "python", phase, target, "0.2.0", {"evidence": "outputs"})
            receipt = self.root / f"{phase}.json"
            write_receipt(receipt, product="sdk", component="python", phase=phase, target=target,
                          version="0.2.0", version_identity="0.2.0", upstream=[], context=self.context,
                          outputs=manifest["outputs"])
            self.args[f"{phase}_stage"], self.args[f"{phase}_receipt"] = stage, receipt
        self.package = load_canonical_json_bytes(self.args["package_receipt"].read_bytes())
        self.value = {"schemaVersion": 2, "kind": "sdk-native-validation-content", "component": "python",
            "target": "linux-x64", "sdkVersion": "0.2.0", "packageOutputsDigest": output_inventory_digest(self.package["outputs"]),
            **{key: "sha256:" + "c" * 64 for key in ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")},
            "files": [], "packageNegativeCases": []}
        self.mutate = lambda fields: None
        self.calls = []

    @contextmanager
    def capture(self, evidence, repository, key, **policy):
        self.assertEqual(self.args["policy_revision"], policy["policy_revision"])
        self.assertEqual("development", policy["required_trust_domain"])
        yield self.root / "synthetic-private.jar"

    def execute(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual([str(self.java), "-jar", str(self.root / "synthetic-private.jar"),
                          "write-native-wrapper-validation-content"], command[:4])
        fields = {key: Path(value) for key, value in zip(command[4::2], command[5::2])}
        for phase in ("package", "validation"):
            self.assertNotEqual(fields[f"--{phase}-stage"], self.args[f"{phase}_stage"])
            self.assertNotEqual(fields[f"--{phase}-receipt"], self.args[f"{phase}_receipt"])
            self.assertEqual(fields[f"--{phase}-receipt"].read_bytes(), self.args[f"{phase}_receipt"].read_bytes())
        self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
        self.mutate(fields)
        fields["--content-output"].write_bytes(canonical_json_bytes(self.value))
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **overrides):
        with patch("ci.products.tooling.verified_tooling_capture", self.capture), \
                patch("ci.products.sdk_validation.subprocess.run", side_effect=self.execute):
            return verify_sdk_validation_projection(**{**self.args, **overrides})

    def test_proof_binds_exact_original_receipt_inventory_and_all_six_identity_fields(self):
        before = regular_file_inventory(self.root)
        proof = self.verify()
        original = self.args["validation_receipt"].read_bytes()
        receipt = load_canonical_json_bytes(original)
        expected = proof.receipt_value(receipt, self.package)
        self.assertEqual(expected["receiptSha256"], sha256_bytes(original))
        self.assertEqual(expected["sha256"], sha256_bytes(canonical_json_bytes(self.value)))
        self.assertEqual(before, regular_file_inventory(self.root))
        with self.assertRaises(TypeError):
            VerifiedSdkValidationProjection(original, canonical_json_bytes(self.value), object())
        for field in ("product", "component", "phase", "target", "productVersion", "buildKey"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                proof.output_inventory(sha256_bytes(original), receipt["outputs"], identity={**receipt, field: "different"})
        with self.assertRaises(ValueError):
            proof.output_inventory(sha256_bytes(original), [], identity=receipt)
        with self.assertRaises(ValueError):
            proof.output_inventory("sha256:" + "0" * 64, receipt["outputs"], identity=receipt)
        for field in ("product", "component", "phase", "target", "productVersion", "outputs"):
            wrong = {**self.package, field: [] if field == "outputs" else "different"}
            with self.subTest(package_field=field), self.assertRaises(ValueError):
                proof.receipt_value(receipt, wrong)

    def test_different_original_producer_receipts_keep_equal_comparison_content(self):
        first = self.verify()
        original = self.args["validation_receipt"].read_bytes()
        receipt = load_canonical_json_bytes(original)
        changed = deepcopy(receipt)
        changed["producer"]["commit"] = "d" * 40
        changed["producer"]["tree"] = "e" * 40
        self.args["validation_receipt"].write_bytes(canonical_json_bytes(changed))
        second = self.verify()
        left = first.receipt_value(receipt, self.package)
        right = second.receipt_value(changed, self.package)
        self.assertEqual(left["sha256"], right["sha256"])
        self.assertNotEqual(left["receiptSha256"], right["receiptSha256"])
        with self.assertRaises(ValueError):
            second.receipt_value(receipt, self.package)
        # Preserve both originals: comparison does not mutate or relabel either proof.
        self.assertEqual(left, first.receipt_value(receipt, self.package))

    def test_wrong_full_gate_content_identity_never_mints_proof(self):
        original = dict(self.value)
        for field, value in (("schemaVersion", True), ("schemaVersion", 1), ("component", "rust"),
                             ("target", "macos-arm64"), ("sdkVersion", "0.2.1"),
                             ("packageOutputsDigest", "sha256:" + "d" * 64), ("producer", "unexpected")):
            self.value = {**original, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify()

    def test_full_gate_failure_or_mutated_private_input_never_mints_proof(self):
        for phase in ("package", "validation"):
            for suffix in ("stage", "receipt"):
                def mutate(fields):
                    path = fields[f"--{phase}-{suffix}"]
                    if suffix == "stage":
                        path = path / "outputs/original.txt"
                    path.write_bytes(path.read_bytes() + b"changed during full gate\n")
                self.mutate = mutate
                with self.subTest(phase=phase, suffix=suffix), self.assertRaises(ValueError):
                    self.verify()
        def failure(fields):
            raise subprocess.CalledProcessError(1, "fixed verifier", b"actual failure")
        self.mutate = failure
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()

    def test_original_swap_and_restore_cannot_change_captured_proof(self):
        def swap(fields):
            path = self.args["validation_receipt"]
            original = path.read_bytes()
            try:
                path.write_bytes(b"temporary untrusted original replacement")
                self.assertEqual(original, fields["--validation-receipt"].read_bytes())
            finally:
                path.write_bytes(original)
        self.mutate = swap
        self.verify()
        self.assertEqual(1, len(self.calls))

    def evidence_record(self):
        return {"receiptSha256": sha256_bytes(self.args["validation_receipt"].read_bytes()),
            "component": self.args["component"], "target": self.args["target"],
            **{name: self.args[argument].relative_to(self.root).as_posix() for name, argument in _EVIDENCE_PATHS.items()}}

    def tooling_policy(self):
        return {"evidence": str(self.args["tooling_evidence"]), "publicKey": str(self.args["tooling_public_key"]),
            "javaExecutable": str(self.java), "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}

    def test_declared_evidence_paths_rebase_without_inheriting_tooling_authority(self):
        record = self.evidence_record()
        decoded = decode_sdk_validation_records(self.root, [record])
        self.assertEqual(self.args["validation_stage"], decoded[record["receiptSha256"]]["validationStage"])
        rebased = rebase_sdk_validation_records([record], self.root, self.root.parent)
        self.assertEqual(f"{self.root.name}/validation", rebased[0]["validationStage"])
        self.assertEqual(record["receiptSha256"], rebased[0]["receiptSha256"])
        for invalid in ({**record, "javaExecutable": "untrusted"}, {**record, "target": "other"},
                        {**record, "validationStage": "../escape"}, {**record, "packageReceipt": "/absolute"}):
            with self.assertRaises(ValueError):
                decode_sdk_validation_records(self.root, [invalid])
        with self.assertRaises(ValueError):
            decode_sdk_validation_records(self.root, [record, record])

    def test_provider_uses_caller_pinned_policy_and_exact_original_receipt(self):
        record, proof = self.evidence_record(), self.verify()
        receipt = load_canonical_json_bytes(self.args["validation_receipt"].read_bytes())
        entry = {**receipt, "receiptSha256": record["receiptSha256"]}
        for policy in ({**self.tooling_policy(), "requiredTrustDomain": "release"},
                       {**self.tooling_policy(), "javaExecutable": "java"},
                       {**self.tooling_policy(), "keyring": str(self.root / "untrusted")}):
            with self.assertRaises(ValueError):
                sdk_validation_provider(self.root, [record], repository=self.root, policy_revision="a" * 40, tooling=policy)
        with patch("ci.products.sdk_validation.verify_sdk_validation_projection", return_value=proof) as full_gate:
            provider = sdk_validation_provider(self.root, [record], repository=self.root, policy_revision="a" * 40,
                                               tooling=self.tooling_policy())
            self.assertIs(proof, provider(entry))
            self.assertIs(proof, provider(entry))
            full_gate.assert_called_once()
            self.assertEqual(self.root, full_gate.call_args.kwargs["repository"])
            self.assertEqual("a" * 40, full_gate.call_args.kwargs["policy_revision"])
            self.assertEqual(self.args["validation_receipt"], full_gate.call_args.kwargs["validation_receipt"])
            for field in ("product", "component", "phase", "target", "productVersion", "buildKey", "receiptSha256"):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    provider({**entry, field: "different"})

    def test_five_host_metadata_keys_require_bound_proofs_and_ignore_original_run_bytes(self):
        from ci.products.registry import PhaseInstanceId, NATIVE_BINDINGS
        from ci.tests.test_product_plan import upstreams, verified_sdk_projections, file_record, VERSIONS, DIGEST_A
        for language in NATIVE_BINDINGS:
            instance = PhaseInstanceId("sdk", language, "metadata", "desktop")
            receipts = upstreams(instance)
            arguments = dict(inventory=[file_record()], versions=VERSIONS, upstream_receipts=receipts,
                             toolchain_profile_digest=DIGEST_A, flags_digest=DIGEST_A)
            proofs = verified_sdk_projections(instance, receipts)
            accepted = plan_phase(instance, **arguments, sdk_validation_projections=proofs)
            for invalid in (None, (), proofs[:-1], tuple(reversed(proofs)), (True,) * 5):
                with self.subTest(language=language, invalid=type(invalid).__name__), self.assertRaises(ValueError):
                    plan_phase(instance, **arguments, sdk_validation_projections=invalid)
            changed = deepcopy(receipts)
            for receipt in changed:
                if receipt["phase"] == "validation":
                    receipt["producer"]["commit"] = "e" * 40
                    receipt["outputs"][0]["sha256"] = "sha256:" + "f" * 64
            replay = plan_phase(instance, **{**arguments, "upstream_receipts": changed},
                                sdk_validation_projections=verified_sdk_projections(instance, changed))
            self.assertEqual(accepted["buildKey"], replay["buildKey"])
            self.assertNotEqual(accepted["inputs"]["upstreamArtifacts"], replay["inputs"]["upstreamArtifacts"])
            for receipt in changed:
                if receipt["phase"] == "package":
                    receipt["outputs"][0]["sha256"] = "sha256:" + "d" * 64
            with self.assertRaises(ValueError):
                plan_phase(instance, **{**arguments, "upstream_receipts": changed}, sdk_validation_projections=proofs)

    def test_direct_metadata_request_routes_all_hosts_through_same_authenticated_provider(self):
        from ci.products.registry import PhaseInstanceId
        from ci.tests.test_product_plan import upstreams, verified_sdk_projections
        instance = PhaseInstanceId("sdk", "python", "metadata", "desktop")
        receipts = upstreams(instance)
        proofs = verified_sdk_projections(instance, receipts)
        validations = [receipt for receipt in receipts if receipt["phase"] == "validation"]
        by_target = {receipt["target"]: proof for receipt, proof in zip(validations, proofs, strict=True)}
        records = sorted(({**self.evidence_record(), "target": receipt["target"],
                            "receiptSha256": sha256_bytes(canonical_json_bytes(receipt))}
                           for receipt in validations), key=lambda record: record["receiptSha256"])
        request = {"artifactRoot": str(self.root), "records": records, "tooling": self.tooling_policy()}
        with patch("ci.products.sdk_validation.verify_sdk_validation_projection",
                   side_effect=lambda **args: by_target[args["target"]]) as gate:
            result = _sdk_validation_projections_from_request(instance, receipts, request, self.root, "a" * 40)
            self.assertEqual(proofs, result)
            self.assertEqual(5, gate.call_count)
            for invalid in (None, {**request, "records": records[:-1]}, {**request, "records": records + records[:1]}):
                with self.assertRaises(ValueError):
                    _sdk_validation_projections_from_request(instance, receipts, invalid, self.root, "a" * 40)

    def comparison_pair(self):
        from ci.tests.test_product_index import producer
        private, public, signing = generate_development_key(self.root / "index-keys")
        records = []
        for number in (1, 2):
            stage, receipt_path = self.args["validation_stage"], self.args["validation_receipt"]
            (stage / "outputs/original.txt").write_bytes(f"synthetic run-specific raw log {number}\n".encode())
            manifest = write_output_manifest(stage, "sdk", "python", "validation", "linux-x64", "0.2.0", {"evidence": "outputs"})
            original_producer = {**producer("development"), "runId": number}
            receipt = write_receipt(receipt_path, product="sdk", component="python", phase="validation", target="linux-x64",
                version="0.2.0", version_identity="0.2.0", upstream=[], context={"producer": original_producer},
                outputs=manifest["outputs"])
            proof = self.verify()  # Full executable gate remains mocked; this tests only comparison orchestration.
            raw = receipt_path.read_bytes()
            index = build_product_index([IndexEntrySource(raw, receipt["outputs"][0]["relativePath"])],
                repository=original_producer["repository"], context={"kind": "pull-request", **{key: original_producer[key]
                    for key in ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
                trust_domain="development", signing=signing, producer=original_producer, stable_history=None)
            index_path = self.root / f"index-{number}.json"
            index_path.write_bytes(canonical_json_bytes(index))
            signature = sign_manifest(index_path, private, signing)
            verified, contents = verify_signed_product_index(SignedProductIndex(index_path, signature), public)
            self.assertEqual(canonical_json_bytes(index), contents)
            archive = store_local_object(stage, receipt_path, self.root / f"objects-{number}")["path"]
            records.append((verified, archive, receipt, proof, RemoteCatalog(index_path, signature,
                {receipt["buildKey"]: archive}, public_key=public)))
        return records

    def test_signed_indexes_and_original_objects_compare_semantics_without_rewriting_provenance(self):
        left, right = self.comparison_pair()
        before = regular_file_inventory(self.root)
        proofs = {item[0]["entries"][0]["receiptSha256"]: item[3] for item in (left, right)}
        provider = lambda entry: proofs[entry["receiptSha256"]]
        self.assertEqual(left[2]["buildKey"], right[2]["buildKey"])
        self.assertNotEqual(left[2]["outputs"], right[2]["outputs"])
        for index, archive, receipt, proof, _ in (left, right):
            self.assertIs(proof, verify_sdk_validation_index_object(index["entries"][0], archive, lambda *_: proof))
        with self.assertRaises(ValueError):
            verify_build_key_output_consistency([left[2], right[2]])
        verify_build_key_output_consistency([left[2], right[2]], sdk_validation_projection=lambda receipt:
                                            proofs[sha256_bytes(canonical_json_bytes(receipt))])
        with self.assertRaises(ValueError):
            verify_immutable_product_indexes(left[0], right[0])
        verify_immutable_product_indexes(left[0], right[0], sdk_validation_projection=provider)
        views = [verified_index_content(item[0]["entries"][0], sdk_validation_projection=provider) for item in (left, right)]
        self.assertEqual(views[0]["outputs"], views[1]["outputs"])
        self.assertNotEqual(views[0]["receiptSha256"], views[1]["receiptSha256"])
        self.assertEqual(before, regular_file_inventory(self.root))

    def test_wrong_object_or_proof_cannot_relax_sdk_comparison(self):
        left, right = self.comparison_pair()
        entry = left[0]["entries"][0]
        for path in (right[1], self.root / "missing.zip"):
            provider = Mock()
            with self.assertRaises(ValueError):
                verify_sdk_validation_index_object(entry, path, provider)
            provider.assert_not_called()

    def test_changed_semantic_content_remains_a_conflict_and_signing_forwards_sdk_proof_inputs(self):
        left, right = self.comparison_pair()
        self.value["canonicalApiDigest"] = "sha256:" + "9" * 64
        changed = self.verify()
        proofs = {left[0]["entries"][0]["receiptSha256"]: left[3], right[0]["entries"][0]["receiptSha256"]: changed}
        with self.assertRaises(ValueError):
            verify_immutable_product_indexes(left[0], right[0], sdk_validation_projection=lambda entry: proofs[entry["receiptSha256"]])
        with self.assertRaises(ValueError):
            verify_build_key_output_consistency([left[2], right[2]], sdk_validation_projection=lambda receipt:
                                                proofs[sha256_bytes(canonical_json_bytes(receipt))])
        objects = {left[0]["entries"][0]["receiptSha256"]: left[1]}
        provider = lambda entry, archive: left[3]
        with patch("ci.products.index.build_product_index", side_effect=ValueError("stop before signing")) as builder:
            with self.assertRaisesRegex(ValueError, "stop before signing"):
                write_signed_product_index([], repository="fixture/repository", context={}, trust_domain="development",
                    signing={}, producer={}, stable_history=None, private_key=self.root / "unused-private",
                    public_key=self.root / "unused-public", manifest_path=self.root / "unused-index",
                    sdk_validation_objects=objects, sdk_validation_projection=provider)
        self.assertEqual(objects, builder.call_args.kwargs["sdk_validation_objects"])
        self.assertIs(provider, builder.call_args.kwargs["sdk_validation_projection"])

    def test_unverified_proof_or_wrong_identity_never_admits_an_original_object(self):
        left, right = self.comparison_pair()
        entry = left[0]["entries"][0]
        for proof in (None, {}, True, object(), right[3]):
            with self.subTest(proof=type(proof).__name__), self.assertRaises(ValueError):
                verify_sdk_validation_index_object(entry, left[1], lambda *_: proof)
            with self.assertRaises(ValueError):
                verify_immutable_product_indexes(left[0], right[0], sdk_validation_projection=lambda _: proof)
        for field in ("product", "component", "phase", "target", "productVersion", "buildKey"):
            provider = Mock()
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_sdk_validation_index_object({**entry, field: "different"}, left[1], provider)
            provider.assert_not_called()

    def test_same_pr_catalog_uses_receipt_qualified_sdk_object_before_comparison(self):
        left, right = self.comparison_pair()
        session = LookupSession(repository=left[0]["repository"], pull_request=31, same_pr=left[4],
                                sdk_validation_projection=lambda entry, archive: left[3])
        session._load_catalog("same-pr", right[4])
        with self.assertRaises(ValueError):
            session._reject_conflicting_catalog_outputs([left[0], right[0]])
        proofs = {item[0]["entries"][0]["receiptSha256"]: item[3] for item in (left, right)}
        session._sdk_validation_projection = lambda entry, archive: proofs[entry["receiptSha256"]]
        session._reject_conflicting_catalog_outputs([left[0], right[0]])
        self.assertEqual(2, len(session._sdk_projections))


if __name__ == "__main__":
    unittest.main()

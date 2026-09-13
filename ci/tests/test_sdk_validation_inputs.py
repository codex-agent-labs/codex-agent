"""Real signed K/R capture; mocked SDK executable admission is transport evidence only."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.index import IndexEntrySource, SignedProductIndex, build_product_index, verify_signed_product_index
from ci.products.restore import object_relative_path, store_local_object
from ci.products.signatures import generate_development_key, sign_manifest
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.selection import classify_paths, phase_inventory_paths
from ci.products.sdk_validation import VerifiedSdkValidationProjection, _VERIFIED, decode_sdk_validation_records
from ci.products.sdk_validation_inputs import REQUEST_NAME, load_sdk_validation_evidence, stage_sdk_validation_evidence
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request


class SdkValidationInputsTest(unittest.TestCase):
    @staticmethod
    def sources(repository, validation, stage, output):
        root = output / "validation-source"
        root.mkdir()
        for name in ("capability-claims.tsv", "test-program-source"):
            (root / name).write_bytes(b"synthetic source; never executed\n")

    @staticmethod
    def proof(**arguments):
        receipt = arguments["validation_receipt"].read_bytes()
        package = load_canonical_json_bytes(arguments["package_receipt"].read_bytes())
        return VerifiedSdkValidationProjection(receipt, canonical_json_bytes({
            "sdkVersion": package["productVersion"], "packageOutputsDigest": output_inventory_digest(package["outputs"]),
        }), _VERIFIED)

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-validation-carrier-test-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        cls.chain = build_chain(cls.root / "signed-fixtures", 37)
        cls.original = cls.root / "original"
        cls.original.mkdir()
        (cls.original / "request.json").write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        context = {"producer": {"repository": "fixture/repository", "workflowPath": ".github/workflows/products.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request", "runId": 7, "runAttempt": 1, "pullRequest": 31}}
        record = {"component": "rust", "target": "linux-x64", "compatibilityRequest": "request.json"}
        for name in ("packageStage", "validationStage", "runtimeStages", "stagedSdks"):
            stage = cls.original / name
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/original.log").write_bytes(b"exact original raw evidence\n")
            record[name] = name
        for phase, target in (("package", "desktop"), ("validation", "linux-x64")):
            manifest = write_output_manifest(cls.original / record[phase + "Stage"], "sdk", "rust", phase,
                                            target, "0.2.9", {"evidence": "outputs"})
            path = cls.original / (phase + "Receipt")
            write_receipt(path, product="sdk", component="rust", phase=phase, target=target, version="0.2.9",
                          version_identity="0.2.9", upstream=[], context=context, outputs=manifest["outputs"])
            record[phase + "Receipt"] = path.name
        record["receiptSha256"] = sha256_bytes((cls.original / "validationReceipt").read_bytes())
        cls.records = [record]
        cls.tooling = {"evidence": str(cls.root / "caller/tooling"), "publicKey": str(cls.root / "caller/public.pub"),
                      "javaExecutable": str(cls.root / "caller/java"), "requiredTrustDomain": "development",
                      "keyring": None, "keysDirectory": None}
        cls.carrier = cls.root / "carrier"
        with patch("ci.products.sdk_validation_inputs._capture_validation_sources", cls.sources), \
                patch("ci.products.sdk_validation.verify_sdk_validation_projection", side_effect=cls.proof):
            cls.captured = stage_sdk_validation_evidence(cls.records, cls.original, cls.carrier,
                repository=cls.root, policy_revision="a" * 40, tooling=cls.tooling)

    def stage(self, records, source, output, *, proof=None, tooling=None):
        with patch("ci.products.sdk_validation_inputs._capture_validation_sources", self.sources), \
                patch("ci.products.sdk_validation.verify_sdk_validation_projection", side_effect=proof or self.proof):
            return stage_sdk_validation_evidence(records, source, output, repository=self.root,
                policy_revision="a" * 40, tooling=self.tooling if tooling is None else tooling)

    def test_relocation_preserves_originals_and_never_transports_tooling_authority(self):
        original_inventory = regular_file_inventory(self.carrier, allow_empty=True)
        self.assertEqual(self.captured, load_sdk_validation_evidence(self.carrier))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            moved = root / "moved"
            snapshot_regular_tree(self.carrier, moved)
            # Hide only this test's synthetic source products, not repository inputs.
            hidden = self.chain["root"].with_name("hidden")
            self.chain["root"].rename(hidden)
            try:
                output = root / "recaptured"
                self.assertEqual(self.captured, self.stage(self.captured, moved, output))
                self.assertEqual(original_inventory, regular_file_inventory(output, allow_empty=True))
                record = decode_sdk_validation_records(output, self.captured)[self.captured[0]["receiptSha256"]]
                for field in ("packageReceipt", "validationReceipt"):
                    self.assertEqual((self.original / self.records[0][field]).read_bytes(), record[field].read_bytes())
                original_request = record["packageReceipt"].parent / "original-compatibility-request.json"
                self.assertEqual((self.original / "request.json").read_bytes(), original_request.read_bytes())
                self.assertNotIn("sdkValidationTooling", (output / REQUEST_NAME).read_text())
                with self.assertRaises(ValueError):
                    self.stage(self.captured, moved, output)
                self.assertEqual(original_inventory, regular_file_inventory(output, allow_empty=True))
            finally:
                hidden.rename(self.chain["root"])

    def test_exact_carrier_rejects_missing_extra_escape_symlink_and_cross_receipt(self):
        for case in ("missing", "extra", "input-extra", "input-escape", "input-absolute", "escape", "symlink", "receipt", "authority"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve() / "carrier"
                snapshot_regular_tree(self.carrier, root)
                records = deepcopy(self.captured)
                receipt = root / records[0]["validationReceipt"]
                if case == "missing":
                    receipt.unlink()
                elif case == "extra":
                    (root / "private-key").write_bytes(b"must never be transported")
                elif case == "input-extra":
                    inputs = (root / records[0]["compatibilityRequest"]).parent
                    (inputs / "private-key").write_bytes(b"self-inventoried is not declared")
                    inventory = inputs / "sdk-inputs-inventory.json"
                    value = load_canonical_json_bytes(inventory.read_bytes())
                    value["files"] = regular_file_inventory(inputs, excluded_paths=(inventory.name,), allow_empty=True)
                    inventory.write_bytes(canonical_json_bytes(value))
                elif case in ("input-escape", "input-absolute"):
                    request = root / records[0]["compatibilityRequest"]
                    value = load_canonical_json_bytes(request.read_bytes())
                    value["contractPayload"] = "../../outside.zip" if case == "input-escape" else str(request.parent / value["contractPayload"])
                    request.write_bytes(canonical_json_bytes(value))
                    inventory = request.parent / "sdk-inputs-inventory.json"
                    value = load_canonical_json_bytes(inventory.read_bytes())
                    value["files"] = regular_file_inventory(request.parent, excluded_paths=(inventory.name,), allow_empty=True)
                    inventory.write_bytes(canonical_json_bytes(value))
                elif case == "escape":
                    records[0]["compatibilityRequest"] = "../outside.json"
                elif case == "symlink":
                    receipt.unlink()
                    receipt.symlink_to(self.carrier / records[0]["validationReceipt"])
                elif case == "receipt":
                    value = load_canonical_json_bytes(receipt.read_bytes())
                    value["producer"]["commit"] = "c" * 40
                    receipt.write_bytes(canonical_json_bytes(value))
                else:
                    records[0]["sdkValidationTooling"] = self.tooling
                (root / REQUEST_NAME).write_bytes(canonical_json_bytes(records))
                with self.assertRaises((ValueError, OSError)):
                    load_sdk_validation_evidence(root)

    def test_full_gate_rejection_mutation_and_caller_policy_fail_before_publication(self):
        def reject(**kwargs):
            raise ValueError("full executable gate rejected")
        def mutate(**kwargs):
            proof = self.proof(**kwargs)
            (kwargs["runtime_stages"] / "outputs/original.log").write_bytes(b"changed captured evidence")
            return proof
        for callback in (reject, mutate):
            with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
                output = Path(temporary).resolve() / "output"
                try:
                    self.stage(self.captured, self.carrier, output, proof=callback)
                finally:
                    self.assertFalse(output.exists())
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
            self.stage(self.captured, self.carrier, Path(temporary).resolve() / "output", tooling={})
        with self.assertRaises(ValueError):
            self.stage(self.captured, self.carrier, self.carrier / "overlap")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            changed = root / "source"
            snapshot_regular_tree(self.carrier, changed)
            record = self.captured[0]
            source = (changed / record["packageReceipt"]).parent / "validation-source/test-program-source"
            source.write_bytes(b"not original Git evidence\n")
            with self.assertRaisesRegex(ValueError, "original Git evidence"):
                self.stage(self.captured, changed, root / "output")

    def test_transport_policy_does_not_invalidate_product_bytes(self):
        path = "ci/products/sdk_validation_inputs.py"
        self.assertEqual(set(PHASE_INSTANCE_IDS), set(classify_paths((path,)).instances))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths((path,), instance))

    def test_outer_capture_retains_complete_sdk_records_and_injects_only_current_authority(self):
        from ci.tests.test_product_reuse_adapter import product_reuse
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / "state/sdk-validation-evidence"
            def stage(records, source, output, **policy):
                self.assertEqual(self.root, policy["repository"])
                self.assertEqual("a" * 40, policy["policy_revision"])
                self.assertEqual(self.tooling, policy["tooling"])
                return self.stage(records, source, output)
            with patch.object(product_reuse, "stage_sdk_validation_evidence", side_effect=stage):
                records = product_reuse._capture_sdk_handoffs((self.carrier,), destination, root,
                    repository=self.root, policy_revision="a" * 40, tooling=self.tooling)
            self.assertEqual(records, product_reuse._retained_sdk_handoffs(root / "state", root))
            request = {"sdkValidationEvidence": records}
            with patch.object(product_reuse, "plan_reuse_wave", return_value={}) as wave:
                product_reuse._plan_with_sdk_tooling(request, self.tooling)
            self.assertEqual(self.tooling, wave.call_args.args[0]["sdkValidationTooling"])
            self.assertNotIn("sdkValidationTooling", request)
            self.assertEqual(self.captured, load_sdk_validation_evidence(destination / "0"))

    def test_catalog_extracts_only_index_bound_sdk_carriers_without_network(self):
        from ci.tests.test_product_reuse_adapter import product_reuse
        from ci.tests.test_product_index import producer
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private, public, signing = generate_development_key(root / "keys")
            record = self.captured[0]
            receipt_path = self.carrier / record["validationReceipt"]
            original = receipt_path.read_bytes()
            receipt = load_canonical_json_bytes(original)
            index_producer = {**producer("development"), "repository": receipt["producer"]["repository"]}
            index = build_product_index([IndexEntrySource(original, receipt["outputs"][0]["relativePath"])],
                repository=index_producer["repository"], context={"kind": "pull-request", **{key: index_producer[key]
                    for key in ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
                trust_domain="development", signing=signing, producer=index_producer, stable_history=None)
            manifest = root / "product-index.json"
            manifest.write_bytes(canonical_json_bytes(index))
            signature = sign_manifest(manifest, private, signing)
            verify_signed_product_index(SignedProductIndex(manifest, signature), public)
            obj = store_local_object(self.carrier / record["validationStage"], receipt_path, root / "cache")["path"]
            object_name = object_relative_path(receipt["buildKey"], record["receiptSha256"])
            # This transport-only fixture supplies the already-observed boundary;
            # testedCommit, not the run's head metadata, binds the signed index.
            workflow_observation = {"run": {
                "id": index_producer["runId"], "run_attempt": index_producer["runAttempt"],
                "head_sha": index_producer["commit"], "path": index_producer["workflowPath"],
            }, "testedCommit": {"sha": index_producer["commit"], "tree": {"sha": index_producer["tree"]}}}
            for case in ("valid", "unindexed", "extra", "missing-receipt",
                         "missing-tested-commit", "wrong-tested-commit", "wrong-tested-tree"):
                with self.subTest(case=case):
                    value = deepcopy(index)
                    observed = deepcopy(workflow_observation)
                    if case == "missing-tested-commit":
                        del observed["testedCommit"]
                    elif case == "wrong-tested-commit":
                        observed["testedCommit"]["sha"] = "c" * 40
                    elif case == "wrong-tested-tree":
                        observed["testedCommit"]["tree"]["sha"] = "d" * 40
                    if case == "unindexed":
                        value["entries"][0]["receiptSha256"] = "sha256:" + "f" * 64
                    archive = root / f"{case}.zip"
                    members = {"product-index.json": canonical_json_bytes(value),
                               "product-index.sig": signature.read_bytes(), "public-key.pub": public.read_bytes(),
                               object_name: obj.read_bytes()}
                    for item in regular_file_inventory(self.carrier, allow_empty=True):
                        name = item["relativePath"]
                        if case == "missing-receipt" and name == record["validationReceipt"]:
                            continue
                        members["sdk-validation-evidence/" + name] = (self.carrier / name).read_bytes()
                    if case == "extra":
                        members["sdk-validation-evidence/private-key"] = b"unrequested secret"
                    with zipfile.ZipFile(archive, "w") as stream:
                        for name, contents in sorted(members.items()):
                            stream.writestr(name, contents)
                    destination = root / case
                    artifact = {"id": 7, "digest": sha256_bytes(archive.read_bytes()),
                                "archive_download_url": "https://example.invalid/never-requested"}
                    with patch.object(product_reuse, "download_artifact", return_value=archive.read_bytes()):
                        if case != "valid":
                            with self.assertRaises((ValueError, OSError)):
                                product_reuse._materialize_catalog("same-pr", artifact, "fixture", destination,
                                    index_producer["repository"], 31, None, observed)
                            continue
                        catalog = product_reuse._materialize_catalog("same-pr", artifact, "fixture", destination,
                            index_producer["repository"], 31, None, observed)
                    self.assertEqual(self.captured, load_sdk_validation_evidence(catalog.sdk_validation_evidence_root))
                    self.assertEqual(original, (catalog.sdk_validation_evidence_root / record["validationReceipt"]).read_bytes())
                    self.assertEqual(obj.read_bytes(), catalog.objects[receipt["buildKey"]].read_bytes())
                    def stage(records, source, output, **policy):
                        return self.stage(records, source, output)
                    with patch.object(product_reuse, "stage_sdk_validation_evidence", side_effect=stage):
                        retained = product_reuse._capture_sdk_handoffs((catalog.sdk_validation_evidence_root,),
                            destination / "sdk-validation-evidence", destination,
                            repository=self.root, policy_revision="a" * 40, tooling=self.tooling)
                    product_reuse._verify_discovery_sdk_records({"sdkValidationEvidence": retained}, destination)
                    with self.assertRaises(ValueError):
                        product_reuse._verify_discovery_sdk_records({}, destination)
                    self.assertEqual(self.captured, load_sdk_validation_evidence(destination / "sdk-validation-evidence/0"))

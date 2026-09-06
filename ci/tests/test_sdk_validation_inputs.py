"""Real signed K/R capture; mocked SDK executable admission is transport evidence only."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from ci.products.receipt import output_inventory_digest, write_output_manifest
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
        context = {"producer": {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local", "runId": None, "runAttempt": None, "pullRequest": None}}
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

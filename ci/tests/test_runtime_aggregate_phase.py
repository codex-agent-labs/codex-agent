"""Original signed synthetic artifacts, not compiler or hosted-runner evidence."""
import copy
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_aggregate_phase
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, write_canonical_json
from products.contract_model import CONTRACT_CHECKSUM_SUFFIXES
from products.receipt import compute_build_key, output_inventory_digest
from products.runtime_aggregate import produce_runtime_aggregate
from ci.tests.test_product_native_chain import build_chain


class RuntimeAggregatePhaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-aggregate-inputs-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        cls.chain = build_chain(cls.root / "original", 41)
        cls.originals = {}
        stages = {tuple(getattr(identity, key) for key in ("component", "phase", "target")): stage
                  for identity, stage in cls.chain["context"]["phase_stages"].items()}
        paths = {(target, phase, target): path
                 for target, values in cls.chain["variants"]["variant_phase_receipts"].items()
                 for phase, path in values.items()}
        paths.update({(record["component"], record["phase"], record["target"]): record["receipt"]
                      for record in cls.chain["adapters"]["adapter_receipts"]})
        for identity, path in paths.items():
            cls.originals[identity] = {"stage": stages[identity], "receiptPath": path,
                                       "receipt": load_canonical_json_bytes(path.read_bytes())}
        receipt = load_canonical_json_bytes(cls.chain["aggregate_receipt"].read_bytes())
        cls.original_plan = {key: receipt[key] for key in (
            "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
        )}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-aggregate-test-", dir=self.root)
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.records = {identity: dict(original) for identity, original in self.originals.items()}
        self.plan = copy.deepcopy(self.original_plan)
        self.calls = []

    def predecessor(self, *identity):
        self.calls.append(identity)
        return self.records[identity]

    def collect(self):
        return runtime_aggregate_phase.collect_inputs(self.plan, self.predecessor)

    def mutant(self, identity, mutate):
        original = self.originals[identity]
        stage = self.work / "stage"
        shutil.copytree(original["stage"], stage)
        receipt = copy.deepcopy(original["receipt"])
        manifest = load_canonical_json_bytes((stage / "output-manifest.json").read_bytes())
        mutate(stage, receipt, manifest)
        write_canonical_json(stage / "output-manifest.json", manifest)
        path = self.work / "receipt.json"
        write_canonical_json(path, receipt)
        self.records[identity] = {"stage": stage, "receiptPath": path, "receipt": receipt}
        if identity[1] == "metadata":
            for reference in self.plan["inputs"]["upstreamArtifacts"]:
                if tuple(reference[key] for key in ("component", "phase", "target")) == identity:
                    reference["outputsDigest"] = output_inventory_digest(receipt["outputs"])
            self.plan["buildKey"] = compute_build_key(product="runtime", component="runtime-aggregate",
                                                       phase="metadata", target="aggregate", inputs=self.plan["inputs"])

    def test_exact_45_originals_feed_existing_full_signed_variant_aggregate_producer(self):
        before = {identity: record["receiptPath"].read_bytes() for identity, record in self.originals.items()}
        result = self.collect()
        self.assertEqual(45, len(self.calls))
        self.assertEqual(set(self.originals), set(self.calls))
        self.assertEqual(25, len(result["adapter_receipts"]))
        self.assertEqual(15, sum(map(len, result["adapter_report_files"].values())))
        self.assertEqual({"variant_bundles", "variant_phase_receipts", "variant_validation_evidence",
                          "runtime_maven_files", "adapter_evidence", "adapter_receipts", "adapter_report_files"}, set(result))
        contract, variants = self.chain["contract"], self.chain["variants"]
        output = self.work / "aggregate"
        output.mkdir()
        produced = produce_runtime_aggregate(
            runtime_version="0.2.7", contract_payload=contract["payload"],
            contract_metadata_receipt=contract["receipt"], contract_attestation=contract["attestation"],
            contract_attestation_signature=contract["signature"],
            contract_public_key=self.chain["context"]["public_key"], required_trust_domain="development",
            output_directory=output,
            **{key: variants[key] for key in ("variant_attestations", "variant_attestation_signatures", "variant_public_keys")},
            **{key: value for key, value in result.items() if key not in {"adapter_receipts", "adapter_report_files"}},
        )
        self.assertEqual(self.chain["aggregate"].read_bytes(), produced["manifestPath"].read_bytes())
        self.assertEqual(before, {identity: record["receiptPath"].read_bytes() for identity, record in self.originals.items()})

    def test_wrong_phase_and_current_plan_predecessor_substitution_reject(self):
        self.plan["phase"] = "binary"
        with self.assertRaisesRegex(ValueError, "identity"):
            self.collect()
        self.assertFalse(self.calls)
        self.plan = copy.deepcopy(self.original_plan)
        self.plan["inputs"]["upstreamArtifacts"][0]["outputsDigest"] = "sha256:" + "b" * 64
        self.plan["buildKey"] = compute_build_key(product="runtime", component="runtime-aggregate", phase="metadata",
                                                   target="aggregate", inputs=self.plan["inputs"])
        with self.assertRaisesRegex(ValueError, "eight metadata"):
            self.collect()

    def test_crosspaired_original_receipt_and_stage_are_rejected(self):
        left, right = ("jvm", "binary", "jvm"), ("node-js", "binary", "node-js")
        self.records[left] = self.originals[right]
        with self.assertRaisesRegex(ValueError, "receipt identity"):
            self.collect()
        self.records[left] = {**self.originals[left], "stage": self.originals[right]["stage"]}
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.collect()

    def test_extra_stage_file_and_symbolic_stage_reject_without_original_changes(self):
        identity = ("jvm", "binary", "jvm")
        stage = self.work / "copied"
        shutil.copytree(self.originals[identity]["stage"], stage)
        (stage / "unexpected").write_bytes(b"extra")
        self.records[identity] = {**self.originals[identity], "stage": stage}
        with self.assertRaises(ValueError):
            self.collect()
        link = self.work / "symbolic"
        link.symlink_to(self.originals[identity]["stage"], target_is_directory=True)
        self.records[identity]["stage"] = link
        with self.assertRaisesRegex(ValueError, "non-symbolic"):
            self.collect()

    def test_coherent_metadata_bytes_cannot_replace_original_report_projection(self):
        def replace(stage, receipt, manifest):
            for record in receipt["outputs"]:
                if record["kind"] == "adapter-evidence":
                    raw = canonical_json_bytes({"wrong": "projection"})
                    (stage / record["relativePath"]).write_bytes(raw)
                    record.update(bytes=len(raw), sha256=sha256_bytes(raw))
            manifest["outputs"] = copy.deepcopy(receipt["outputs"])
        self.mutant(("jvm", "metadata", "jvm"), replace)
        with self.assertRaisesRegex(ValueError, "projection differs"):
            self.collect()

    def test_missing_native_maven_is_a_real_required_producer_input_not_reconstructed(self):
        def remove(stage, receipt, manifest):
            for record in receipt["outputs"]:
                if record["kind"] == "maven":
                    (stage / record["relativePath"]).unlink()
            receipt["outputs"] = [record for record in receipt["outputs"] if record["kind"] != "maven"]
            manifest["outputs"] = copy.deepcopy(receipt["outputs"])
        self.mutant(("linux-arm64", "package", "linux-arm64"), remove)
        with self.assertRaisesRegex(ValueError, "original linux-arm64 Maven"):
            self.collect()

    def test_coherent_crosspaired_maven_primary_cannot_replace_original_publication(self):
        foreign = self.originals[("node-js", "metadata", "node-js")]
        foreign_primary = next(record for record in foreign["receipt"]["outputs"]
                               if record["relativePath"] == "outputs/maven/node-js/runtime.bin")
        replacement = (foreign["stage"] / foreign_primary["relativePath"]).read_bytes()
        original_binary = self.originals[("jvm", "binary", "jvm")]["receiptPath"].read_bytes()
        original_package = self.originals[("jvm", "package", "jvm")]["receiptPath"].read_bytes()

        def replace(stage, receipt, manifest):
            for record in receipt["outputs"]:
                if record["kind"] != "maven":
                    continue
                suffix = next((value for value in CONTRACT_CHECKSUM_SUFFIXES
                               if record["relativePath"].endswith(value)), None)
                raw = (hashlib.new(suffix[1:], replacement).hexdigest().encode() + b"\n"
                       if suffix else replacement)
                (stage / record["relativePath"]).write_bytes(raw)
                record.update(bytes=len(raw), sha256=sha256_bytes(raw))
            manifest["outputs"] = copy.deepcopy(receipt["outputs"])

        # The substitute has coherent hashes, all checksum sidecars, stage and
        # receipt inventories, and the corresponding newly keyed aggregate plan.
        self.mutant(("jvm", "metadata", "jvm"), replace)
        with self.assertRaisesRegex(ValueError, "differs from its original binary publication"):
            self.collect()
        self.assertEqual(original_binary, self.originals[("jvm", "binary", "jvm")]["receiptPath"].read_bytes())
        self.assertEqual(original_package, self.originals[("jvm", "package", "jvm")]["receiptPath"].read_bytes())

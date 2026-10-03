"""Original signed synthetic artifacts, not compiler or hosted-runner evidence."""
import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_aggregate_phase
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, write_canonical_json
from products.receipt import compute_build_key, output_inventory_digest, write_output_manifest
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

    def test_finalized_aggregate_translates_exact_original_manifest_maven_and_receipt(self):
        stage = self.chain["root"] / "aggregate-stage"
        before = {path: path.read_bytes() for path in stage.rglob("*") if path.is_file()}
        receipt = self.chain["aggregate_receipt"].read_bytes()
        result = runtime_aggregate_phase.collect_finalized_inputs(
            stage, self.chain["aggregate_receipt"], "0.2.0", self.predecessor)
        self.assertEqual(self.chain["aggregate"], result["manifest"])
        self.assertEqual(self.chain["aggregate_receipt"], result["metadata_receipt"])
        self.assertEqual(260, len(result["runtime_maven_files"]))
        self.assertNotIn("publication_inputs", result)
        self.assertEqual(receipt, self.chain["aggregate_receipt"].read_bytes())
        self.assertEqual(before, {path: path.read_bytes() for path in stage.rglob("*") if path.is_file()})

    def test_finalized_stage_rejects_extra_missing_and_crosspaired_outputs(self):
        stage = self.work / "final-stage"
        shutil.copytree(self.chain["root"] / "aggregate-stage", stage)
        extra = stage / "extra"
        extra.write_bytes(b"undeclared")
        with self.assertRaises(ValueError):
            runtime_aggregate_phase.collect_finalized_inputs(
                stage, self.chain["aggregate_receipt"], "0.2.0", self.predecessor)
        extra.unlink()
        manifest = stage / "outputs" / self.chain["aggregate"].name
        original = manifest.read_bytes()
        manifest.write_bytes(original + b"mutation")
        with self.assertRaises(ValueError):
            runtime_aggregate_phase.collect_finalized_inputs(
                stage, self.chain["aggregate_receipt"], "0.2.0", self.predecessor)
        manifest.unlink()
        with self.assertRaises(ValueError):
            runtime_aggregate_phase.collect_finalized_inputs(
                stage, self.chain["aggregate_receipt"], "0.2.0", self.predecessor)

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
                          "publication_inputs", "adapter_evidence", "adapter_receipts", "adapter_report_files"}, set(result))
        self.assertEqual(8, len(result.pop("publication_inputs")))
        result["runtime_maven_files"] = self.chain["adapters"]["runtime_maven_files"]
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

    def test_missing_native_publication_is_a_required_original_not_reconstructed(self):
        def remove(stage, receipt, manifest):
            for record in receipt["outputs"]:
                if record["kind"] == "publication":
                    (stage / record["relativePath"]).unlink()
            receipt["outputs"] = [record for record in receipt["outputs"] if record["kind"] != "publication"]
            manifest["outputs"] = copy.deepcopy(receipt["outputs"])
        self.mutant(("linux-arm64", "binary", "linux-arm64"), remove)
        with self.assertRaisesRegex(ValueError, "original linux-arm64 publication"):
            self.collect()

    def test_coherent_crosspaired_maven_primary_cannot_replace_original_publication(self):
        from ci.tests.test_product_runtime_maven import runtime_maven_fixture
        originals = {}
        for component in (*runtime_aggregate_phase.RUNTIME_TARGETS, *runtime_aggregate_phase.RUNTIME_ADAPTERS):
            phase = "package" if component in runtime_aggregate_phase.RUNTIME_ADAPTERS else "binary"
            original = self.originals[(component, phase, component)]
            originals[component] = {Path(record["relativePath"]).name:
                (original["stage"] / record["relativePath"]).read_bytes()
                for record in original["receipt"]["outputs"] if record["kind"] == "publication"}
        originals["jvm"]["main.jar"] = originals["node-js"]["main.klib"]
        _, contents = runtime_maven_fixture("0.2.7", "0.2.0", original_primaries=originals)
        stage = self.work / "fresh-maven-stage"
        for relative, raw in contents.items():
            path = stage / "outputs" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        write_output_manifest(stage, "runtime", "runtime-aggregate", "metadata", "aggregate", "0.2.7",
                              {"maven": "outputs/maven"})
        original_binary = self.originals[("jvm", "binary", "jvm")]["receiptPath"].read_bytes()
        original_package = self.originals[("jvm", "package", "jvm")]["receiptPath"].read_bytes()

        # Maven POM/GMM/file hashes and stage declaration are coherent, but the
        # substituted primary cannot replace the immutable original binary.
        with self.assertRaisesRegex(ValueError, "differs from its original binary publication"):
            runtime_aggregate_phase.collect_maven_outputs(stage, "0.2.7", "0.2.0", self.predecessor)
        self.assertEqual(original_binary, self.originals[("jvm", "binary", "jvm")]["receiptPath"].read_bytes())
        self.assertEqual(original_package, self.originals[("jvm", "package", "jvm")]["receiptPath"].read_bytes())

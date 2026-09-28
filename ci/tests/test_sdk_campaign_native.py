"""Native campaign orchestration fixtures; mocks do not replace host evidence."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.index import IndexEntrySource
from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from ci.products.sdk_campaign_native import NATIVE_CAMPAIGN_INSTANCES, verify_sdk_campaign_native
from ci.tests.product_chain_support import write_receipt


class _Projection:
    def __init__(self, receipt, raw):
        self.receipt, self.raw = receipt, raw
        self.checked = False

    def output_inventory(self, digest, outputs, *, identity):
        if digest != sha256_bytes(self.raw) or outputs != self.receipt["outputs"] or identity != self.receipt:
            raise ValueError("Wrong original host receipt")
        self.checked = True
        return []


class NativeCampaignTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-native-campaign-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.sources, self.stages, self.receipts = {}, {}, {}
        producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        for position, instance in enumerate(sorted(NATIVE_CAMPAIGN_INSTANCES)):
            directory = self.root / str(position)
            stage = directory / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            path = directory / "receipt.json"
            receipt = write_receipt(path, product="sdk", component=instance.component,
                phase=instance.phase, target=instance.target, version="0.8.0",
                version_identity="0.8.0", outputs=manifest["outputs"], upstream=[],
                context={"producer": producer})
            self.sources[instance] = IndexEntrySource(path.read_bytes(), "outputs/fixture/content.bin")
            self.stages[instance], self.receipts[instance] = stage, receipt

    def _run(self, *, package=None):
        calls = {"package": [], "validation": [], "metadata": []}
        proofs = {}

        def package_gate(repository, stage_root, receipt_path, compatibility_request, **options):
            component = Path(stage_root).parts[-3]
            instance = PhaseInstanceId("sdk", component, "package", "desktop")
            self.assertEqual(Path(receipt_path).read_bytes(), self.sources[instance].receipt_bytes)
            expected = {"runtime_stage_root": self.root / "runtime",
                        "staged_sdks": self.root / "sdks"}
            if component == "csharp":
                binary = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
                self.assertEqual(Path(options["binary_receipt_path"]).read_bytes(),
                                 self.sources[binary].receipt_bytes)
                self.assertEqual(Path(options["binary_stage_root"]).parts[-3:],
                                 ("csharp", "binary", "desktop"))
                expected.update(binary_stage_root=options["binary_stage_root"],
                                binary_receipt_path=options["binary_receipt_path"])
            self.assertEqual(options, expected)
            calls["package"].append(instance)
            if package is not None:
                package(instance)
            return self.receipts[instance], self.sources[instance].receipt_bytes

        def validation_gate(**options):
            instance = PhaseInstanceId("sdk", options["component"], "validation", options["target"])
            self.assertEqual(options["validation_receipt"].read_bytes(), self.sources[instance].receipt_bytes)
            self.assertEqual(options["package_receipt"].read_bytes(), self.sources[
                PhaseInstanceId("sdk", instance.component, "package", "desktop")].receipt_bytes)
            calls["validation"].append(instance)
            proof = _Projection(self.receipts[instance], self.sources[instance].receipt_bytes)
            proofs[instance] = proof
            return proof

        def metadata_gate(**options):
            component = options["component"]
            instance = PhaseInstanceId("sdk", component, "metadata", "desktop")
            self.assertEqual(options["metadata_receipt"].read_bytes(), self.sources[instance].receipt_bytes)
            for target in sorted(NATIVE_TARGETS):
                host = PhaseInstanceId("sdk", component, "validation", target)
                self.assertEqual((options["validation_receipts"] / f"{target}.json").read_bytes(),
                                 self.sources[host].receipt_bytes)
                self.assertTrue(proofs[host].checked)
            self.assertEqual(options["sdk_validation_projections"], tuple(
                proofs[PhaseInstanceId("sdk", component, "validation", target)]
                for target in sorted(NATIVE_TARGETS)))
            calls["metadata"].append(instance)
            return self.receipts[instance], self.sources[instance].receipt_bytes

        with patch("ci.products.sdk_campaign_native.verify_sdk_package_inputs", side_effect=package_gate), \
             patch("ci.products.sdk_campaign_native.verify_sdk_validation_projection", side_effect=validation_gate), \
             patch("ci.products.sdk_campaign_native.verify_sdk_native_metadata_admission", side_effect=metadata_gate):
            result = verify_sdk_campaign_native(repository=self.root, sources=self.sources, stages=self.stages,
                compatibility_request=self.root / "compatibility.json", runtime_stages=self.root / "runtime",
                staged_sdks=self.root / "sdks", tooling_evidence=self.root / "tooling.json",
                tooling_public_key=self.root / "key.pem", java_executable=self.root / "java",
                policy_revision="test", required_trust_domain="development")
        return result, calls, proofs

    def test_all_35_original_receipts_and_25_opaque_projections(self):
        (receipts, projections), calls, proofs = self._run()
        self.assertEqual(set(receipts), NATIVE_CAMPAIGN_INSTANCES)
        self.assertEqual(set(projections), set(proofs))
        self.assertEqual(len(calls["package"]), len(NATIVE_BINDINGS))
        self.assertEqual(len(calls["validation"]), len(NATIVE_BINDINGS) * len(NATIVE_TARGETS))
        self.assertEqual(len(calls["metadata"]), len(NATIVE_BINDINGS))
        for instance, value in receipts.items():
            self.assertEqual(value, (self.receipts[instance], self.sources[instance].receipt_bytes))
        self.assertTrue(all(projections[instance] is proof for instance, proof in proofs.items()))

    def test_missing_or_cross_paired_selection_rejected_before_gates(self):
        first, second = sorted(NATIVE_CAMPAIGN_INSTANCES)[:2]
        sources = dict(self.sources)
        del sources[first]
        with self.assertRaisesRegex(ValueError, "exact 36"):
            verify_sdk_campaign_native(repository=self.root, sources=sources, stages=self.stages,
                compatibility_request=self.root, runtime_stages=self.root, staged_sdks=self.root,
                tooling_evidence=self.root, tooling_public_key=self.root, java_executable=self.root,
                policy_revision="test", required_trust_domain="development")
        self.sources[first], self.sources[second] = self.sources[second], self.sources[first]
        with self.assertRaisesRegex(ValueError, "wrong phase identity"):
            self._run()

    def test_original_stage_mutation_during_gate_fails(self):
        first = min(NATIVE_CAMPAIGN_INSTANCES)
        def mutate(_instance):
            (self.stages[first] / "outputs/fixture/content.bin").write_bytes(b"mutated")
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self._run(package=mutate)


if __name__ == "__main__":
    unittest.main()

"""Private-lifetime reuse, not signed/hosted acceptance (SDK matcher mocked)."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from ci.products.sdk_validation_inputs import (
    collection_admission_scope, sdk_validation_provider,
    append_shared_sdk_validation_evidence, load_sdk_validation_evidence, stage_sdk_validation_evidence,
)
from ci.tests import test_sdk_validation_inputs as fixtures


class SdkCollectionAdmissionTest(unittest.TestCase):
    sources = staticmethod(fixtures.SdkValidationInputsTest.sources)
    proof = staticmethod(fixtures.SdkValidationInputsTest.proof)

    @classmethod
    def setUpClass(cls):
        fixtures.SdkValidationInputsTest.setUpClass.__func__(cls)
        (cls.root / "ci").mkdir()
        (cls.root / "ci/verifier.py").write_bytes(b"synthetic verifier input\n")
        caller = cls.root / "caller"
        (caller / "tooling").mkdir(parents=True)
        (caller / "tooling/evidence.json").write_bytes(b"synthetic signed tooling input\n")
        for name in ("public.pub", "java"):
            (caller / name).write_bytes(b"synthetic caller policy\n")

    def stage(self, source, destination):
        return stage_sdk_validation_evidence(load_sdk_validation_evidence(source), source, destination,
            repository=self.root, policy_revision="a" * 40, tooling=self.tooling)

    def test_collector_and_advance_share_one_gate_under_identical_bytes_and_policy(self):
        @collection_admission_scope
        def collect(root):
            first, shared, advanced = (root / name for name in ("first", "shared", "advanced"))
            self.stage(self.carrier, first)
            append_shared_sdk_validation_evidence(first, shared)
            self.stage(shared, advanced)
            self.assertEqual(regular_file_inventory(first, allow_empty=True),
                             regular_file_inventory(self.carrier, allow_empty=True))
            self.assertEqual(regular_file_inventory(shared, allow_empty=True),
                             regular_file_inventory(advanced, allow_empty=True))

        with tempfile.TemporaryDirectory() as temporary, \
                patch("ci.products.sdk_validation_inputs._capture_validation_sources", self.sources), \
                patch("ci.products.sdk_validation.verify_sdk_validation_projection", side_effect=self.proof) as gate:
            root = Path(temporary).resolve()
            collect(root)
            self.assertEqual(1, gate.call_count)
            self.stage(self.carrier, root / "another-process-lifetime")
            self.assertEqual(2, gate.call_count)

    def test_changed_evidence_policy_or_source_cannot_hit_and_failed_gate_is_not_cached(self):
        for changed in ("evidence", "publicKey", "javaExecutable", "verifier", "revision"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary, \
                    patch("ci.products.sdk_validation_inputs._capture_validation_sources", self.sources), \
                    patch("ci.products.sdk_validation.verify_sdk_validation_projection", side_effect=self.proof) as gate:
                root = Path(temporary).resolve()
                source = root / "carrier"
                snapshot_regular_tree(self.carrier, source)
                mutation = (source / self.captured[0]["runtimeStages"] / "outputs/original.log" if changed == "evidence"
                    else self.root / "ci/verifier.py" if changed == "verifier"
                    else Path(self.tooling[changed]) if changed != "revision" else None)
                original = mutation.read_bytes() if mutation else None

                @collection_admission_scope
                def collect():
                    self.stage(source, root / "first")
                    self.assertEqual(1, gate.call_count)
                    if mutation:
                        mutation.write_bytes(original + b"changed")
                    gate.side_effect = ValueError("full gate rejects changed input")
                    for name in ("second", "retry"):
                        with self.assertRaisesRegex(ValueError, "full gate rejects"):
                            stage_sdk_validation_evidence(load_sdk_validation_evidence(source), source, root / name,
                                repository=self.root, policy_revision=("b" if changed == "revision" else "a") * 40,
                                tooling=self.tooling)
                        self.assertFalse((root / name).exists())
                    self.assertEqual(3, gate.call_count)
                try:
                    collect()
                finally:
                    if mutation:
                        mutation.write_bytes(original)

    def test_captured_provider_cannot_escape_collection_lifetime(self):
        @collection_admission_scope
        def obtain():
            return sdk_validation_provider(self.carrier, self.captured,
                repository=self.root, policy_revision="a" * 40, tooling=self.tooling)
        provider = obtain()
        raw = (self.carrier / self.captured[0]["validationReceipt"]).read_bytes()
        with self.assertRaisesRegex(ValueError, "outside.*lifetime"):
            provider({**load_canonical_json_bytes(raw), "receiptSha256": self.captured[0]["receiptSha256"]})


if __name__ == "__main__":
    unittest.main()

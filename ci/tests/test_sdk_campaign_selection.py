"""Structural SDK campaign selection fixtures, not hosted release evidence."""

from pathlib import Path
import tempfile
import unittest

from ci.products.index import IndexEntrySource
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object
from ci.products.sdk_campaign_selection import (
    SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection, verify_sdk_campaign_selection,
)
from ci.tests.product_chain_support import write_receipt


class SdkCampaignSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-campaign-selection-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.sources, cls.envelopes, cls.archives, cls.stages = {}, {}, {}, {}
        producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
                    "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
                    "runId": 3, "runAttempt": 1, "pullRequest": 31}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            directory = cls.root / str(position)
            stage = directory / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            receipt = write_receipt(directory / "planned.json", product="sdk",
                component=instance.component, phase=instance.phase, target=instance.target,
                version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": producer})
            plan = {name: receipt[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            shard = directory / "shard"
            finalized = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=producer, product_version="0.8.0", trust_domain="development",
                destination=shard)
            cls.sources[instance] = IndexEntrySource(finalized["receiptBytes"],
                "outputs/fixture/content.bin")
            cls.envelopes[instance] = {name: finalized[name] for name in (
                "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
            cls.archives[instance] = shard / finalized["objectPath"]
            cls.stages[instance] = stage

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_exact_selection(self):
        selected = verify_sdk_campaign_selection(
            self.sources, self.envelopes, self.archives, self.stages)
        self.assertEqual(set(selected), SDK_CAMPAIGN_INSTANCES)
        self.assertEqual({receipt["productVersion"] for receipt in selected.values()}, {"0.8.0"})

    def test_partial_or_cross_paired_selection_fails(self):
        first, second = sorted(SDK_CAMPAIGN_INSTANCES)[:2]
        with self.assertRaisesRegex(ValueError, "every exact SDK phase"):
            verify_sdk_campaign_selection({key: value for key, value in self.sources.items()
                if key != first}, self.envelopes, self.archives, self.stages)
        envelopes = dict(self.envelopes)
        envelopes[first], envelopes[second] = envelopes[second], envelopes[first]
        with self.assertRaisesRegex(ValueError, "wrong phase identity"):
            verify_sdk_campaign_selection(self.sources, envelopes, self.archives, self.stages)

    def test_wrong_object_or_changed_stage_fails(self):
        first = min(SDK_CAMPAIGN_INSTANCES)
        envelopes = dict(self.envelopes)
        envelopes[first] = {**envelopes[first], "objectSha256": "sha256:" + "0" * 64}
        with self.assertRaisesRegex(ValueError, "expected transport identity"):
            verify_sdk_campaign_selection(self.sources, envelopes, self.archives, self.stages)
        file = self.stages[first] / "outputs/fixture/content.bin"
        original = file.read_bytes()
        try:
            file.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_sdk_campaign_selection(self.sources, self.envelopes,
                    self.archives, self.stages)
        finally:
            file.write_bytes(original)

    def test_held_selection_uses_private_exact_stages_and_detects_late_change(self):
        first = min(SDK_CAMPAIGN_INSTANCES)
        with held_sdk_campaign_selection(self.sources, self.envelopes,
                self.archives, self.stages) as (sources, envelopes, stages, receipts):
            self.assertEqual(set(stages), SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(sources[first].receipt_bytes, self.sources[first].receipt_bytes)
            self.assertEqual(envelopes[first], self.envelopes[first])
            self.assertEqual(receipts[first]["productVersion"], "0.8.0")
            self.assertNotEqual(stages[first], self.stages[first])
            self.assertEqual((stages[first] / "outputs/fixture/content.bin").read_bytes(),
                             (self.stages[first] / "outputs/fixture/content.bin").read_bytes())
        with self.assertRaisesRegex(ValueError, "Held SDK campaign selection changed"):
            with held_sdk_campaign_selection(self.sources, self.envelopes,
                    self.archives, self.stages) as (_, _, stages, _):
                (stages[first] / "outputs/fixture/content.bin").write_bytes(b"changed")
        extra = self.stages[first] / "unrelated-file"
        try:
            with self.assertRaisesRegex(ValueError, "Held SDK campaign selection changed"):
                with held_sdk_campaign_selection(self.sources, self.envelopes,
                        self.archives, self.stages):
                    extra.write_bytes(b"late")
        finally:
            extra.unlink(missing_ok=True)
        original_digest = self.envelopes[first]["objectSha256"]
        try:
            with self.assertRaises(ValueError):
                with held_sdk_campaign_selection(self.sources, self.envelopes,
                        self.archives, self.stages):
                    self.envelopes[first]["objectSha256"] = "sha256:" + "0" * 64
        finally:
            self.envelopes[first]["objectSha256"] = original_digest


if __name__ == "__main__":
    unittest.main()

"""Source-only SDK promoted catalog closure; no hosted transport is implied."""

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import sha256_file
from ci.products.restore import finalize_phase_object, object_relative_path, verify_object
from ci.products.sdk_catalog_promotion import stage_promoted_sdk_catalog
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.tests import test_sdk_campaign_index as fixture_module


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class SdkCatalogPromotionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.SdkCampaignIndexTest.setUpClass()
        cls.fixture = fixture_module.SdkCampaignIndexTest

    @classmethod
    def tearDownClass(cls):
        fixture_module.SdkCampaignIndexTest.tearDownClass()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-promoted-catalog-test-")
        self.root = Path(self.temporary.name).resolve()
        self.pins = {}
        for instance in SDK_CAMPAIGN_INSTANCES:
            source = self.fixture.sources[instance]
            envelope = self.fixture.envelopes[instance]
            self.pins[instance] = {
                "buildKey": envelope["receipt"]["buildKey"],
                "receiptSha256": envelope["receiptSha256"],
                "objectSha256": envelope["objectSha256"],
                "artifactPath": source.artifact_path,
                "producer": envelope["receipt"]["producer"],
            }
        self.producer = {**self.fixture.producer, "event": "push", "pullRequest": None,
                         "commit": "c" * 40, "tree": "d" * 40, "runId": 9}
        self.context = {"kind": "promoted-main", "commit": self.producer["commit"],
                        "tree": self.producer["tree"], "promotionRunId": 9,
                        "promotionRunAttempt": 1}

    def tearDown(self):
        self.temporary.cleanup()

    def _stage(self, *, pins=None, objects=None, signed=None, context=None,
               expected_index_sha256=None, expected_signature_sha256=None):
        signed = signed or self.fixture.source
        return stage_promoted_sdk_catalog(
            objects or self.fixture.archives, pins or self.pins, signed,
            self.root / "promoted", repository=self.fixture.repository,
            campaign_context=self.fixture.context,
            expected_index_sha256=expected_index_sha256 or sha256_file(signed.manifest),
            expected_signature_sha256=expected_signature_sha256 or sha256_file(signed.signature),
            context=context or self.context, producer=self.producer,
            keyring=self.fixture.keyring, keys_directory=self.fixture.keys_directory,
            private_key=self.fixture.private_key)

    def test_promoted_index_retains_exact_original_object_and_receipt_bytes(self):
        promoted = self._stage()
        output = self.root / "promoted"
        verified, _ = verify_release_product_index(SignedProductIndex(
            output / "product-index.json", output / "product-index.sig"),
            keyring_path=self.fixture.keyring, keys_directory=self.fixture.keys_directory)
        self.assertEqual(promoted, verified)
        self.assertEqual(len(verified["entries"]), 62)
        self.assertEqual(verified["context"], self.context)
        for instance in SDK_CAMPAIGN_INSTANCES:
            pin = self.pins[instance]
            archive = output / object_relative_path(pin["buildKey"], pin["receiptSha256"])
            self.assertEqual(archive.read_bytes(), self.fixture.archives[instance].read_bytes())
            self.assertEqual(verify_object(archive, build_key=pin["buildKey"],
                receipt_sha256=pin["receiptSha256"])["receiptBytes"],
                self.fixture.sources[instance].receipt_bytes)

    def test_wrong_independent_pin_or_signed_pair_fails_closed(self):
        instance = min(SDK_CAMPAIGN_INSTANCES)
        pins = deepcopy(self.pins)
        pins[instance]["objectSha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "protected object pin"):
            self._stage(pins=pins)
        with self.assertRaisesRegex(ValueError, "protected digest pins"):
            self._stage(expected_index_sha256="sha256:" + "0" * 64)
        pins = deepcopy(self.pins)
        pins[instance]["producer"]["commit"] = "e" * 40
        with self.assertRaisesRegex(ValueError, "protected pin"):
            self._stage(pins=pins)

    def test_incomplete_or_wrong_promotion_context_fails(self):
        pins = dict(self.pins)
        pins.pop(min(SDK_CAMPAIGN_INSTANCES))
        with self.assertRaisesRegex(ValueError, "62 elected"):
            self._stage(pins=pins)
        with self.assertRaisesRegex(ValueError, "push promoted-main"):
            self._stage(context={**self.context, "kind": "stable"})

    def test_signed_campaign_can_promote_mixed_original_producers(self):
        instance = min(SDK_CAMPAIGN_INSTANCES)
        original = self.fixture.envelopes[instance]["receipt"]
        plan = {name: original[name] for name in (
            "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        older_push = {**self.fixture.producer, "event": "push", "pullRequest": None,
                      "commit": "e" * 40, "tree": "f" * 40, "runId": 2}
        finalized = finalize_phase_object(stage_root=self.fixture.stages[instance],
            phase_plan=plan, producer=older_push, product_version="0.8.0",
            trust_domain="development", destination=self.root / "older-shard")
        pins = deepcopy(self.pins)
        pins[instance].update(receiptSha256=finalized["receiptSha256"],
                              objectSha256=finalized["objectSha256"], producer=older_push)
        objects = dict(self.fixture.archives)
        objects[instance] = self.root / "older-shard" / finalized["objectPath"]
        changed = deepcopy(self.fixture.index)
        entry = next(entry for entry in changed["entries"] if
            (entry["product"], entry["component"], entry["phase"], entry["target"]) ==
            (instance.product, instance.component, instance.phase, instance.target))
        entry["receiptSha256"] = finalized["receiptSha256"]
        signed = self.fixture._signed(changed, "mixed-producer")
        self._stage(pins=pins, objects=objects, signed=signed)
        archived = self.root / "promoted" / object_relative_path(
            pins[instance]["buildKey"], pins[instance]["receiptSha256"])
        self.assertEqual(verify_object(archived, build_key=pins[instance]["buildKey"],
            receipt_sha256=pins[instance]["receiptSha256"])["receipt"]["producer"], older_push)

    def test_signer_rejects_observation_token_before_signing(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "synthetic-token"}):
            with self.assertRaisesRegex(ValueError, "observation token"):
                self._stage()
        self.assertFalse((self.root / "promoted").exists())

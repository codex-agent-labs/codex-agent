"""Release-signed SDK catalog admission without rewriting original receipts."""

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import sha256_file
from ci.products.restore import object_relative_path
from ci.products.reuse import LookupSession, RemoteCatalog, ReuseLookupError
from ci.products.sdk_campaign_index import verify_release_sdk_campaign_objects
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.sdk_catalog_promotion import stage_promoted_sdk_catalog
from ci.tests import test_sdk_campaign_index as fixture_module


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class SdkReleaseCampaignObjectsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.SdkCampaignIndexTest.setUpClass()
        cls.fixture = fixture_module.SdkCampaignIndexTest
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-release-objects-test-")
        cls.root = Path(cls.temporary.name).resolve()
        pins = {instance: {
            "buildKey": envelope["receipt"]["buildKey"],
            "receiptSha256": envelope["receiptSha256"],
            "objectSha256": envelope["objectSha256"],
            "artifactPath": cls.fixture.sources[instance].artifact_path,
            "producer": envelope["receipt"]["producer"],
        } for instance, envelope in cls.fixture.envelopes.items()}
        producer = {**cls.fixture.producer, "event": "push", "pullRequest": None,
                    "commit": "c" * 40, "tree": "d" * 40, "runId": 9}
        context = {"kind": "promoted-main", "commit": producer["commit"],
                   "tree": producer["tree"], "promotionRunId": 9, "promotionRunAttempt": 1}
        destination = cls.root / "promoted"
        stage_promoted_sdk_catalog(cls.fixture.archives, pins, cls.fixture.source,
            destination, repository=cls.fixture.repository,
            campaign_context=cls.fixture.context,
            expected_index_sha256=sha256_file(cls.fixture.source.manifest),
            expected_signature_sha256=sha256_file(cls.fixture.source.signature),
            context=context, producer=producer, keyring=cls.fixture.keyring,
            keys_directory=cls.fixture.keys_directory, private_key=cls.fixture.private_key)
        cls.index, _ = verify_release_product_index(SignedProductIndex(
            destination / "product-index.json", destination / "product-index.sig"),
            keyring_path=cls.fixture.keyring, keys_directory=cls.fixture.keys_directory)
        cls.objects = {entry["buildKey"]: destination / object_relative_path(
            entry["buildKey"], entry["receiptSha256"]) for entry in cls.index["entries"]}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        fixture_module.SdkCampaignIndexTest.tearDownClass()

    def verify(self, *, index=None, objects=None):
        return verify_release_sdk_campaign_objects(index or self.index,
            self.objects if objects is None else objects, repository=self.fixture.repository)

    def test_promoted_index_authenticates_all_originals_without_rewriting_receipts(self):
        originals = self.verify()
        self.assertEqual(SDK_CAMPAIGN_INSTANCES, set(originals))
        for instance, original in originals.items():
            self.assertEqual("development", original["receipt"]["trustDomain"])
            self.assertEqual(self.fixture.sources[instance].receipt_bytes,
                             original["receiptBytes"])

    def test_missing_or_swapped_original_fails_closed(self):
        keys = sorted(self.objects)
        missing = dict(self.objects)
        missing.pop(keys[0])
        with self.assertRaisesRegex(ValueError, "exact indexed original objects"):
            self.verify(objects=missing)
        swapped = dict(self.objects)
        swapped[keys[0]] = swapped[keys[1]]
        with self.assertRaises(ValueError):
            self.verify(objects=swapped)

        tampered = self.root / "tampered-original.zip"
        changed = bytearray(self.objects[keys[0]].read_bytes())
        changed[len(changed) // 2] ^= 1
        tampered.write_bytes(changed)
        substituted = dict(self.objects)
        substituted[keys[0]] = tampered
        with self.assertRaises(ValueError):
            self.verify(objects=substituted)

    def test_non_exact_or_non_promoted_index_fails_closed(self):
        shortened = deepcopy(self.index)
        shortened["entries"].pop()
        with self.assertRaisesRegex(ValueError, "every exact SDK campaign phase"):
            self.verify(index=shortened)
        wrong_context = deepcopy(self.index)
        wrong_context["context"]["kind"] = "stable"
        with self.assertRaises(ValueError):
            self.verify(index=wrong_context)

    def test_promoted_lookup_keeps_original_receipt_and_rejects_missing_lineage(self):
        instance = min(SDK_CAMPAIGN_INSTANCES)
        original = self.fixture.envelopes[instance]
        receipt = original["receipt"]
        plan = {name: receipt[name] for name in (
            "product", "component", "phase", "target", "buildKey", "inputs")}
        manifest = self.root / "promoted/product-index.json"
        signature = self.root / "promoted/product-index.sig"

        def session(objects):
            catalog = RemoteCatalog(manifest, signature, objects,
                keyring=self.fixture.keyring, keys_directory=self.fixture.keys_directory)
            return LookupSession(repository=self.fixture.repository, pull_request=None,
                                 promoted_main=catalog)

        found = session(self.objects).lookup("promoted-main", plan)
        self.assertEqual(original["receiptBytes"], found.envelope["receiptBytes"])
        self.assertEqual("development", found.envelope["receipt"]["trustDomain"])
        missing = dict(self.objects)
        missing.pop(next(key for key in missing if key != receipt["buildKey"]))
        with self.assertRaisesRegex(ReuseLookupError, "corrupt"):
            session(missing).lookup("promoted-main", plan)


if __name__ == "__main__":
    unittest.main()

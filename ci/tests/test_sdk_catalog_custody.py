"""Local-only failed-catalog custody; synthetic keys grant no production trust."""

import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci.sdk_catalog_custody import (
    PUBLIC_KEY, RECORD, SIGNATURE, prepare_failed_sdk_catalog_custody,
    verify_failed_sdk_catalog_custody,
)
from ci.sdk_catalog_custody_signer import sign_prepared_failed_sdk_catalog_custody
from ci.sdk_campaign_original_locator import failed_sdk_partial_catalog_name
from ci.sdk_campaign_original_locator import products as sdk_products
from ci.tests import test_sdk_campaign_reused_original as reused_fixture
from ci.tests import test_sdk_worker_collection as fixture_module
from ci.products.inventory import (
    canonical_json_bytes, publish_regular_tree, regular_file_inventory, sha256_bytes,
)
from ci.products.signatures import generate_development_key


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class FailedSdkCatalogCustodyTest(unittest.TestCase):
    def setUp(self):
        self.base = reused_fixture.ReusedSdkOriginalTest(
            methodName="test_failed_run_partial_catalog_preserves_successful_original_worker")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        base = self.base
        self.producer = base.fixture.producer
        base.catalog_artifact["name"] = failed_sdk_partial_catalog_name(self.producer)
        base.run = {**base.run, "status": "completed", "conclusion": "failure"}
        self.root = base.fixture.repository / "custody-test"
        self.root.mkdir()
        self.private, public, metadata = generate_development_key(self.root / "signer")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        (self.keys / "fixture-release.pub").write_bytes(public.read_bytes())
        self.policy = self.root / "product-signing-keys.json"
        self.policy.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": metadata["namespace"],
            "algorithm": metadata["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": "fixture-release", "fingerprint": metadata["fingerprint"]},
            "retiredKeys": [],
        }))
        self.keyring_sha = sha256_bytes(self.policy.read_bytes())
        self.keys_sha = sha256_bytes(canonical_json_bytes(regular_file_inventory(self.keys)))
        self.source = fixture_module.PIN
        self.route = {"trusted_workflow_sha": fixture_module.PIN,
            "trusted_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_job_name": base.catalog_job["name"]}
        self.selection = {"producer": self.producer, "artifact_id": 902,
            "artifact_sha256": sha256_bytes(base.raw), **self.route,
            "trusted_source_commit": self.source,
            "keyring_path": self.policy, "keys_directory": self.keys,
            "expected_keyring_sha256": self.keyring_sha,
            "expected_keys_inventory_sha256": self.keys_sha}

    def prepare(self, **changes):
        path = self.root / "prepared"
        with self.base.official():
            result = prepare_failed_sdk_catalog_custody(**(self.selection | changes),
                token="synthetic-token", destination=path)
        return path, result

    def sign(self, prepared, **changes):
        signed = self.root / "signed"
        arguments = {"expected_record_sha256": sha256_bytes((prepared / RECORD).read_bytes()),
            "trusted_source_commit": self.source,
            "keyring_path": self.policy, "keys_directory": self.keys,
            "expected_keyring_sha256": self.keyring_sha,
            "expected_keys_inventory_sha256": self.keys_sha,
            "private_key": self.private}
        with patch.object(sdk_products, "api_json", side_effect=AssertionError("signer must not query GitHub")):
            sign_prepared_failed_sdk_catalog_custody(prepared, signed, **(arguments | changes))
        return signed

    def verify(self, signed, **changes):
        return verify_failed_sdk_catalog_custody(signed, **(self.selection | changes))

    def test_exact_official_failed_upload_can_be_signed_and_reused(self):
        prepared, record = self.prepare()
        self.assertEqual("development-cache-only", record["scope"])
        self.assertEqual({PUBLIC_KEY, RECORD}, {p.name for p in prepared.iterdir()})
        signed = self.sign(prepared)
        self.assertEqual({PUBLIC_KEY, RECORD, SIGNATURE}, {p.name for p in signed.iterdir()})
        selected = self.verify(signed)
        self.assertEqual(self.base.key.read_bytes(), Path(selected["publicKey"]).read_bytes())
        self.assertEqual(sha256_bytes(self.base.key.read_bytes()), selected["publicKeySha256"])

    def test_wrong_official_digest_fails_before_download(self):
        with self.base.official(), patch.object(sdk_products, "download_artifact_to_file") as download, \
                self.assertRaisesRegex(ValueError, "caller-pinned official identity"):
            prepare_failed_sdk_catalog_custody(**(self.selection | {
                "artifact_sha256": "sha256:" + "0" * 64}), token="synthetic-token",
                destination=self.root / "rejected")
        download.assert_not_called()

    def test_signed_policy_rejects_wrong_route_keyring_and_public_key(self):
        prepared, _ = self.prepare()
        signed = self.sign(prepared)
        for changed in ({"trusted_job_name": "product-validation / wrong-job"},
                        {"expected_keyring_sha256": "sha256:" + "0" * 64},
                        {"trusted_source_commit": "0" * 40}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.verify(signed, **changed)
        (signed / PUBLIC_KEY).write_bytes(self.base.other_key.read_bytes())
        with self.assertRaisesRegex(ValueError, "key differs from signed record"):
            self.verify(signed)

    def test_signer_rejects_unpinned_record_and_development_signer(self):
        prepared, _ = self.prepare()
        with self.assertRaisesRegex(ValueError, "independent record pin"):
            self.sign(prepared, expected_record_sha256="sha256:" + "0" * 64)
        record = json.loads((prepared / RECORD).read_bytes())
        record["signing"]["trustDomain"] = "development"
        (prepared / RECORD).write_bytes(canonical_json_bytes(record))
        with self.assertRaisesRegex(ValueError, "not release trust"):
            self.sign(prepared)

    def test_signature_and_inactive_product_key_fail_closed(self):
        prepared, _ = self.prepare()
        signed = self.sign(prepared)
        signature = signed / SIGNATURE
        signature.write_bytes(signature.read_bytes().replace(b"A", b"B", 1))
        with self.assertRaises(ValueError):
            self.verify(signed)
        policy = json.loads(self.policy.read_bytes())
        policy["activeKey"] = None
        self.policy.write_bytes(canonical_json_bytes(policy))
        with self.base.official(), patch.object(sdk_products, "api_json") as official, \
                self.assertRaisesRegex(ValueError, "No active release"):
            prepare_failed_sdk_catalog_custody(**(self.selection | {
                "expected_keyring_sha256": sha256_bytes(self.policy.read_bytes())}),
                token="synthetic-token", destination=self.root / "inactive")
        official.assert_not_called()

    def test_late_mutation_cannot_change_published_custody_bytes(self):
        def mutate_prepared(source, destination, **options):
            (source / PUBLIC_KEY).write_bytes(self.base.other_key.read_bytes())
            publish_regular_tree(source, destination, **options)
        with patch("ci.sdk_catalog_custody.publish_regular_tree", side_effect=mutate_prepared), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.prepare()
        self.assertFalse((self.root / "prepared").exists())
        prepared, _ = self.prepare()

        def mutate_signed(source, destination, **options):
            (source / SIGNATURE).write_bytes(b"tampered signature\n")
            publish_regular_tree(source, destination, **options)
        with patch("ci.sdk_catalog_custody_signer.publish_regular_tree", side_effect=mutate_signed), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.sign(prepared)
        self.assertFalse((self.root / "signed").exists())


if __name__ == "__main__":
    unittest.main()

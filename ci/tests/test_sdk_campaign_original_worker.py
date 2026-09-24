"""Fresh SDK upload observation: synthetic API responses, real shard bytes."""

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from ci import sdk_campaign_original_worker as worker
from ci.tests import test_sdk_worker_collection as fixture_module
from ci.tests.test_product_resume_capture import archive
from products.inventory import canonical_json_bytes, sha256_bytes
from ci.sdk_campaign_observation import ObservedSdkOriginal


class SdkCampaignOriginalWorkerTest(TestCase):
    def setUp(self):
        self.fixture = fixture_module.SdkWorkerCollectionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.instance, self.ready, shard, self.descriptor, self.files = self.fixture.shard("package")
        self.raw = archive(self.files)
        self.record = {"product": self.instance.product, "component": self.instance.component,
            "phase": self.instance.phase, "target": self.instance.target,
            "buildKey": self.ready["buildKey"], "receiptSha256": self.descriptor["receiptSha256"],
            "objectSha256": self.descriptor["objectSha256"], "state": "retained",
            "source": None, "transportSource": None, "misses": []}
        self.original = ObservedSdkOriginal(self.descriptor["receiptBytes"],
            canonical_json_bytes(self.record), shard / self.descriptor["objectPath"],
            shard.parent / "stage")
        self.transport = canonical_json_bytes({"captureProducer": self.fixture.producer})

    def observe(self, *, original=None, artifact_id=901, digest=None):
        original = self.original if original is None else original
        return worker.held_fresh_sdk_worker_upload(
            self.instance, original, self.transport, artifact_id=artifact_id,
            artifact_sha256=sha256_bytes(self.raw) if digest is None else digest,
            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token", environ={})

    def test_exact_original_receipt_object_job_and_upload(self):
        self.assertIs(worker.ObservedSdkOriginal, ObservedSdkOriginal)
        with self.fixture.official_api({self.instance: self.ready}, {self.instance: self.raw}) as (query, _, download):
            with self.observe() as (evidence, extracted):
                self.assertEqual(self.descriptor["receiptSha256"], evidence["originalReceiptSha256"])
                self.assertEqual(self.descriptor["objectSha256"], evidence["originalObjectSha256"])
                self.assertEqual(901, evidence["artifact"]["id"])
                self.assertEqual(self.original.receipt_bytes,
                                 (extracted / "shard/phase-receipt.json").read_bytes())
            self.assertEqual(3, query.call_count)
            download.assert_called_once()

    def test_reused_or_crosspaired_original_rejects_before_observation(self):
        reused = replace(self.original, replay_record_canonical=canonical_json_bytes({
            **self.record, "state": "reused", "source": "same-pr",
            "transportSource": {"kind": "same-pr"}}))
        with patch.object(worker.product_reuse, "api_json") as query, \
             self.assertRaisesRegex(ValueError, "exact retained original"):
            with self.observe(original=reused):
                pass
        query.assert_not_called()
        wrong = replace(self.original, receipt_bytes=self.original.receipt_bytes + b" ")
        with patch.object(worker.product_reuse, "api_json") as query, self.assertRaises(ValueError):
            with self.observe(original=wrong):
                pass
        query.assert_not_called()

    def test_wrong_official_id_or_digest_rejects(self):
        with self.fixture.official_api({self.instance: self.ready}, {self.instance: self.raw}) as (query, _, _):
            official = query.side_effect
            query.side_effect = lambda url, token: official(
                url.replace("/artifacts/902", "/artifacts/901"), token)
            with self.assertRaisesRegex(ValueError, "uploaded artifact differs"):
                with self.observe(artifact_id=902):
                    pass
        with self.fixture.official_api({self.instance: self.ready}, {self.instance: self.raw}):
            with self.assertRaisesRegex(ValueError, "uploaded artifact differs"):
                with self.observe(digest="sha256:" + "0" * 64):
                    pass

    def test_official_upload_with_different_shard_cannot_replace_original(self):
        mutated = {**self.files,
            "shard/phase-receipt.json": self.original.receipt_bytes + b" "}
        raw = archive(mutated)
        with self.fixture.official_api({self.instance: self.ready}, {self.instance: raw}):
            with self.assertRaises(ValueError):
                with self.observe(digest=sha256_bytes(raw)):
                    pass

    def test_signed_context_rejects_before_observation(self):
        with patch.object(worker.product_reuse, "api_json") as query, \
             self.assertRaisesRegex(ValueError, "signing-secret context"):
            with worker.held_fresh_sdk_worker_upload(self.instance, self.original,
                    self.transport, artifact_id=901, artifact_sha256=sha256_bytes(self.raw),
                    trusted_workflow_sha=fixture_module.PIN, token="synthetic-token",
                    environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}):
                pass
        query.assert_not_called()

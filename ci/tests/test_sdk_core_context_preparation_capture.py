"""Core14 preparation transport checks; these are not release or all11 proof."""

import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from ci import sdk_core_context_preparation_capture as capture
from products.inventory import canonical_json_bytes, publish_regular_tree, regular_file_inventory, sha256_bytes


class CorePreparationCaptureTest(unittest.TestCase):
    def setUp(self):
        from ci.tests.test_sdk_core_context_preparation_locator import CorePreparationLocatorTest

        self.fixture = CorePreparationLocatorTest("test_fixed_original_job_and_exact_caller_outputs_only")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture.f
        self.output = self.f.work / "prepared-capture"
        self.context = {"repositoryRoot": "/candidate", "metadataRequest": "/candidate/request.json"}
        self.signing = {"algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                        "trustDomain": "release", "keyId": "test-release",
                        "fingerprint": "sha256:" + "f" * 64}
        self.record = {"schemaVersion": 1, "kind": "sdk-core-metadata-original-context",
                       "buildKey": self.fixture.receipt["buildKey"],
                       "receiptSha256": sha256_bytes(self.fixture.receipt_path.read_bytes()),
                       "artifactId": 702, "artifactSha256": "sha256:" + "e" * 64,
                       "producer": self.f.producer, "originalContext": self.context,
                       "signing": self.signing}
        self.archive()

    def archive(self, extra=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("original-context.json", canonical_json_bytes(self.record))
            if extra is not None:
                archive.writestr("extra.json", extra)
        self.f.raw = output.getvalue()
        self.f.artifact.update(digest=sha256_bytes(self.f.raw), size_in_bytes=len(self.f.raw))
        self.fixture.listing = [self.f.artifact]

    def api(self, url, token):
        if "/actions/runs/71/artifacts?" in url:
            return json.dumps({"artifacts": self.fixture.listing}).encode()
        return self.f.api(url, token)

    def call(self, **changes):
        arguments = {"expected_receipt_sha256": self.record["receiptSha256"],
                     "metadata_artifact_id": 702, "metadata_artifact_sha256": self.record["artifactSha256"],
                     "preparation_artifact_id": 701, "preparation_artifact_sha256": self.f.artifact["digest"],
                     "original_context": self.context, "expected_signing": self.signing,
                     "trusted_workflow_sha": self.f.pin, "repository_root": self.f.root,
                     "environ": {}, "token": "synthetic-token"}
        with patch.object(capture.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return capture.capture_core_context_preparation(self.f.plan_path, self.fixture.receipt_path,
                self.output, **(arguments | changes))

    def test_exact_observed_transport_and_selected_record_are_retained(self):
        transport = self.call()
        self.assertEqual(701, transport["artifact"]["id"])
        self.assertEqual(self.f.raw, (self.output / "transport.zip").read_bytes())
        self.assertEqual(canonical_json_bytes(self.record),
                         (self.output / "original/original-context.json").read_bytes())
        self.assertEqual(self.fixture.receipt_path.read_bytes(),
                         (self.output / "selection/metadata-receipt.json").read_bytes())
        self.assertEqual(5, len(regular_file_inventory(self.output)))

    def test_wrong_record_and_extra_member_reject_without_destination(self):
        for change in ("metadata-id", "context", "signing", "extra"):
            self.record["artifactId"] = 702
            self.record["originalContext"] = self.context
            self.record["signing"] = self.signing
            if change == "metadata-id": self.record["artifactId"] = 703
            elif change == "context": self.record["originalContext"] = {
                **self.context, "metadataRequest": "/candidate/other.json"}
            elif change == "signing": self.record["signing"] = {
                **self.signing, "keyId": "other-release"}
            self.archive(b"extra" if change == "extra" else None)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_late_prepared_member_mutation_cannot_publish(self):
        def mutate_before_copy(source, destination, **kwargs):
            member = Path(source) / "original/original-context.json"
            member.write_bytes(member.read_bytes() + b"late mutation\n")
            return publish_regular_tree(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.call()
        self.assertFalse(self.output.exists())

    def test_extracted_member_change_before_record_verification_cannot_publish(self):
        actual_extract = capture.products.safe_extract

        def mutate_after_extract(archive, destination, **kwargs):
            result = actual_extract(archive, destination, **kwargs)
            member = Path(destination) / "original-context.json"
            member.write_bytes(member.read_bytes() + b"pre-pin mutation\n")
            return result

        with patch.object(capture.products, "safe_extract", side_effect=mutate_after_extract), \
                self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

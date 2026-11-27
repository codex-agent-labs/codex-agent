"""Campaign routing fixtures; mocked semantic readers are not release evidence."""

import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes
from ci.products.sdk_campaign_javascript import verify_campaign_javascript
from ci.tests import test_sdk_javascript_metadata as fixture_module


class JavaScriptCampaignTest(unittest.TestCase):
    def setUp(self):
        fixture = fixture_module.SdkJavaScriptMetadataTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.calls = []
        self.changed_metadata = False
        self.mutate_envelope = False
        self.arguments = {**fixture.args,
            "compatibility_request": fixture.root / "compatibility.json",
            "runtime_package_stage": fixture.root / "runtime-package",
            "runtime_package_receipt": fixture.root / "runtime-package.json"}
        for phase in ("package", "validation", "metadata"):
            raw = fixture.receipt_paths[phase].read_bytes()
            self.arguments[f"{phase}_envelope"] = {
                "receipt": fixture.receipts[phase], "receiptBytes": raw,
                "receiptSha256": sha256_bytes(raw), "objectSha256": "sha256:" + "1" * 64}

    def package(self, *args, **kwargs):
        self.calls.append("package")
        self.assertEqual(args[:4], (self.arguments["repository"],
            self.arguments["package_stage"], self.arguments["package_receipt"],
            self.arguments["compatibility_request"]))
        self.assertEqual(kwargs["runtime_package_stage"], self.arguments["runtime_package_stage"])
        return self.fixture.receipts["package"], self.fixture.receipt_paths["package"].read_bytes()

    def validation(self, **kwargs):
        self.calls.append("validation")
        self.assertEqual(kwargs["runtime_validation_receipt"], self.arguments["runtime_validation_receipt"])
        self.assertEqual(kwargs["original_consumer_directory"], self.arguments["original_consumer_directory"])
        return self.fixture.receipts["validation"], self.fixture.receipt_paths["validation"].read_bytes()

    def metadata(self, **kwargs):
        self.calls.append("metadata")
        self.assertEqual(kwargs["metadata_receipt"], self.arguments["metadata_receipt"])
        if self.mutate_envelope:
            self.arguments["package_envelope"]["objectSha256"] = "sha256:" + "2" * 64
        raw = self.fixture.receipt_paths["metadata"].read_bytes()
        return self.fixture.receipts["metadata"], b"different" if self.changed_metadata else raw

    def verify(self, **overrides):
        with patch("ci.products.sdk_campaign_javascript.verify_sdk_package_inputs", self.package), \
                patch("ci.products.sdk_campaign_javascript.verify_sdk_javascript_validation_phase", self.validation), \
                patch("ci.products.sdk_campaign_javascript.verify_sdk_javascript_metadata_admission", self.metadata):
            return verify_campaign_javascript(**(self.arguments | overrides))

    def test_all_three_full_readers_must_return_exact_selected_originals(self):
        selected = self.verify()
        self.assertEqual(self.calls, ["package", "validation", "metadata"])
        self.assertEqual(set(selected), {"package", "validation", "metadata"})
        for phase, raw in selected.items():
            self.assertEqual(raw, self.fixture.receipt_paths[phase].read_bytes())

    def test_crosspaired_receipt_or_behavior_cannot_be_returned(self):
        package = self.arguments["package_envelope"]
        validation = self.arguments["validation_envelope"]
        with self.assertRaisesRegex(ValueError, "wrong phase identity"):
            self.verify(package_envelope=validation, validation_envelope=package)
        self.assertEqual(self.calls, [])
        self.changed_metadata = True
        with self.assertRaisesRegex(ValueError, "full metadata gate"):
            self.verify()
        self.assertEqual(self.calls, ["package", "validation", "metadata"])
        self.calls.clear()
        self.changed_metadata = False
        self.mutate_envelope = True
        with self.assertRaisesRegex(ValueError, "selected envelope changed"):
            self.verify()
        self.assertEqual(self.calls, ["package", "validation", "metadata"])


if __name__ == "__main__":
    unittest.main()

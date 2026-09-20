"""Transport bootstrap checks for a current elected iOS validation worker.

Hosted API responses are synthetic, but the uploaded ZIP contains a real
finalized phase shard.  This capture elects and retains a receipt; it does not
grant validation-content or signing authority.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.receipt import compute_build_key
from ci.products.signing_isolation import SIGNING_SECRET
from ci.tests import test_sdk_ios_package_upload as fixtures

capture = fixtures.capture


class SdkAppleValidationBootstrapTest(unittest.TestCase):
    def setUp(self):
        # Compose the real-shard/official-API fixture without inheriting its tests.
        self.source = fixtures.SdkIosValidationUploadTest(
            "test_exact_original_archive_plan_shard_and_empty_streams_are_preserved"
        )
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.environment = {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"}
        self.original_plan = self.source.plan_path.read_bytes()
        self.original_receipt = self.source.files["shard/phase-receipt.json"]

    def call(self, *, live_secret=False, **changes):
        arguments = {
            "target": self.source.target,
            "expected_build_key": json.loads(self.original_receipt)["buildKey"],
            "artifact_id": 701,
            "artifact_sha256": self.source.artifact["digest"],
            "trusted_workflow_sha": self.source.pin,
            "repository_root": self.source.root,
            "environ": self.environment,
            "token": "synthetic-token",
            **changes,
        }
        live = {SIGNING_SECRET: ""} if live_secret else {}
        with patch.dict(os.environ, live, clear=True), \
                patch.object(capture, "_validate_plan", return_value=self.source.plan), \
                patch("reuse.api_request", side_effect=self.source.api):
            return capture.capture_elected_sdk_ios_validation_upload(
                self.source.plan_path, self.source.output, **arguments,
            )

    def uploaded_receipt(self, **changes):
        receipt = deepcopy(json.loads(self.original_receipt))
        receipt.update(changes)
        if "target" in changes or "inputs" in changes:
            receipt["buildKey"] = compute_build_key(**{
                name: receipt[name] for name in ("product", "component", "phase", "target", "inputs")
            })
        self.source.files["shard/phase-receipt.json"] = canonical_json_bytes(receipt)
        self.source.archive()
        return receipt

    def test_current_election_retains_exact_real_shard_receipt_and_transport(self):
        source_before = regular_file_inventory(self.source.root, allow_empty=True)
        result = self.call()

        receipt_path = self.source.output / "original/shard/phase-receipt.json"
        self.assertEqual(self.original_receipt, receipt_path.read_bytes())
        self.assertEqual(sha256_bytes(self.original_receipt), result["validationReceiptSha256"])
        self.assertEqual(self.source.producer, result["captureProducer"])
        self.assertEqual(self.source.artifact, result["artifact"])
        self.assertEqual(self.source.raw, (self.source.output / "transport.zip").read_bytes())
        self.assertEqual(self.original_plan, (self.source.output / "plan/impact-plan.json").read_bytes())
        self.assertEqual(
            {"capture-transport.json", "original", "plan", "transport.zip"},
            {path.name for path in self.source.output.iterdir()},
        )
        self.assertEqual(b"", (self.source.output / "original/worker/stdout.bin").read_bytes())
        self.assertEqual(
            result,
            json.loads((self.source.output / "capture-transport.json").read_bytes()),
        )
        self.assertEqual(source_before, regular_file_inventory(self.source.root, allow_empty=True))

    def test_target_key_and_authorization_reject_before_observation(self):
        cases = (
            {"target": "ios"},
            {"target": "IOS-ARM64"},
            {"expected_build_key": "bad"},
            {"expected_build_key": None},
        )
        for changes in cases:
            with self.subTest(changes=changes), patch.object(
                capture, "_observe_ci_producer_jobs"
            ) as observe, self.assertRaises(ValueError):
                self.call(**changes)
            observe.assert_not_called()
            self.assertFalse(self.source.output.exists())

        self.source.plan["remoteBuildAuthorized"] = False
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()
        self.assertFalse(self.source.output.exists())

    def test_uploaded_shard_must_match_current_producer_elected_key_and_target(self):
        baseline = deepcopy(self.source.files)
        original_key = json.loads(self.original_receipt)["buildKey"]
        for case in ("producer", "key", "target"):
            self.source.files = deepcopy(baseline)
            receipt = json.loads(self.original_receipt)
            if case == "producer":
                self.uploaded_receipt(producer={**receipt["producer"], "runAttempt": 1})
            elif case == "key":
                inputs = deepcopy(receipt["inputs"])
                inputs["inventory"].append({
                    "relativePath": "source/elected-key-change.kt",
                    "bytes": 1,
                    "sha256": sha256_bytes(b"x"),
                })
                inputs["phaseInputDigest"] = sha256_bytes(canonical_json_bytes(inputs["inventory"]))
                self.uploaded_receipt(inputs=inputs)
            else:
                self.uploaded_receipt(target="ios-simulator-arm64")
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call(expected_build_key=original_key)
            self.assertFalse(self.source.output.exists())

    def test_signing_secret_is_rejected_at_entry_and_when_introduced_before_publication(self):
        for supplied, live in ((True, False), (False, True)):
            environment = self.environment
            if supplied:
                self.environment = {**environment, SIGNING_SECRET: ""}
            try:
                with self.subTest(supplied=supplied), patch.object(
                    capture, "_observe_ci_producer_jobs"
                ) as observe, self.assertRaisesRegex(ValueError, "signing-secret"):
                    self.call(live_secret=live)
                observe.assert_not_called()
                self.assertFalse(self.source.output.exists())
            finally:
                self.environment = environment

        gate = capture._require_artifact_job_window

        def introduce_secret(*arguments):
            gate(*arguments)
            self.environment[SIGNING_SECRET] = ""

        try:
            with patch.object(capture, "_require_artifact_job_window", side_effect=introduce_secret), \
                    self.assertRaisesRegex(ValueError, "signing-secret"):
                self.call()
            self.assertFalse(self.source.output.exists())
        finally:
            self.environment.pop(SIGNING_SECRET, None)

    def test_late_plan_and_downloaded_archive_mutations_never_publish(self):
        gate = capture._require_artifact_job_window

        def mutate_plan(*arguments):
            gate(*arguments)
            self.source.plan_path.write_bytes(self.original_plan + b"changed\n")

        try:
            with patch.object(capture, "_require_artifact_job_window", side_effect=mutate_plan), \
                    self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.source.output.exists())
        finally:
            self.source.plan_path.write_bytes(self.original_plan)

        extract = capture.safe_extract

        def mutate_archive(archive, destination, *arguments, **keywords):
            result = extract(archive, destination, *arguments, **keywords)
            archive = Path(archive)
            archive.write_bytes(archive.read_bytes() + b"changed after extraction")
            return result

        with patch.object(capture, "safe_extract", side_effect=mutate_archive), \
                self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.source.output.exists())

    def test_changed_current_producer_cannot_publish_bootstrapped_receipt(self):
        gate = capture._require_artifact_job_window
        original = dict(self.environment)

        def mutate(*arguments):
            gate(*arguments)
            self.environment["GITHUB_RUN_ATTEMPT"] = "3"

        try:
            with patch.object(capture, "_require_artifact_job_window", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "current producer changed"):
                self.call()
            self.assertFalse(self.source.output.exists())
        finally:
            self.environment.clear()
            self.environment.update(original)

    def test_output_overlap_and_existing_output_reject_before_http(self):
        for destination in (self.source.root / "nested", self.source.plan_path):
            self.source.output = destination
            with self.subTest(destination=destination), patch.object(
                capture, "_observe_ci_producer_jobs"
            ) as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()

        self.source.output = self.source.work / "occupied"
        self.source.output.mkdir()
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()


if __name__ == "__main__":
    unittest.main()

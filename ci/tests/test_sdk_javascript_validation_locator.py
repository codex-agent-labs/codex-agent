"""Real receipt/CI metadata parsers, mocked HTTP; no original content authority."""

from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_upload as fixture
from ci.tests.product_chain_support import write_receipt
from ci import sdk_javascript_validation_locator as locator
from products.inventory import canonical_json_bytes


class SdkJavaScriptValidationLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.path = self.f.root / "original-validation.json"
        self.receipt = write_receipt(self.path, product="sdk", component="javascript", phase="validation", target="node",
            version="0.2.7", version_identity="0.2.7", outputs=self.f.receipt["outputs"], upstream=[],
            context={"producer": self.f.producer})
        self.raw = self.path.read_bytes()
        self.f.jobs[0]["name"] = "product-validation / sdk-javascript-validation-node"
        self.f.artifact["name"] = ("codex-agent-sdk-worker-javascript-validation-node-"
            + self.receipt["buildKey"].removeprefix("sha256:") + "-" + self.f.producer["tree"] + "-attempt-2")
        self.listing = [deepcopy(self.f.artifact)]
        self.requests = []

    def api(self, url, token):
        self.requests.append(url)
        self.assertFalse(url.endswith("/zip"), "Locator cannot download or admit payload bytes")
        if "/actions/runs/71/artifacts?" in url:
            self.assertEqual("synthetic-token", token)
            return json.dumps({"artifacts": self.listing}).encode()
        return self.f.api(url, token)

    def call(self, **changes):
        with patch("reuse.api_request", side_effect=self.api):
            return locator.locate_javascript_validation_upload(self.path, **{
                "trusted_workflow_sha": self.f.pin, "token": "synthetic-token", **changes})

    def test_exact_original_attempt_key_and_tree_ignore_current_environment_and_newer_uploads(self):
        self.listing += [{**self.f.artifact, "id": 702, "name": self.f.artifact["name"].replace("attempt-2", "attempt-3")},
                         {**self.f.artifact, "id": 703, "expired": True}]
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "8"}):
            self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
        self.assertEqual(self.raw, self.path.read_bytes())
        self.assertEqual(1, sum("/actions/runs/71/artifacts?" in url for url in self.requests))
        self.assertEqual(1, sum(url.endswith("/actions/artifacts/701") for url in self.requests))
        self.assertFalse(self.f.output.exists())

    def test_missing_duplicate_expired_wrong_key_attempt_and_malformed_metadata_reject(self):
        original = deepcopy(self.f.artifact)
        for case in ("missing", "duplicate", "expired", "key", "attempt", "id", "digest"):
            self.listing = [deepcopy(original)]
            if case == "missing": self.listing = []
            elif case == "duplicate": self.listing.append(deepcopy(original))
            elif case == "expired": self.listing[0]["expired"] = True
            elif case == "key": self.listing[0]["name"] = original["name"].replace(self.receipt["buildKey"].removeprefix("sha256:"), "0" * 64)
            elif case == "attempt": self.listing[0]["name"] = original["name"].replace("attempt-2", "attempt-1")
            elif case == "id": self.listing[0]["id"] = True
            else: self.listing[0]["digest"] = "invalid"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()

    def test_observed_job_pin_run_window_and_detail_pairing_reject(self):
        baseline = deepcopy((self.f.run, self.f.jobs, self.f.artifact))
        for case in ("attempt", "job", "failure", "pin", "run", "head", "window", "timestamp", "detail", "url"):
            self.f.run, self.f.jobs, self.f.artifact = deepcopy(baseline)
            if case == "attempt": self.f.run["run_attempt"] = 1
            elif case == "job": self.f.jobs[0]["name"] += "-other"
            elif case == "failure": self.f.jobs[0]["conclusion"] = "failure"
            elif case == "pin": self.f.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "run": self.f.artifact["workflow_run"]["id"] = 72
            elif case == "head": self.f.artifact["workflow_run"]["head_sha"] = "d" * 40
            elif case == "window": self.f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif case == "timestamp": del self.f.artifact["created_at"]
            elif case == "url": self.f.artifact["archive_download_url"] = "https://elsewhere.invalid/archive"
            self.listing = [deepcopy(self.f.artifact)]
            if case == "detail": self.f.artifact["digest"] = "sha256:" + "f" * 64
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()

    def test_wrong_receipt_scope_local_source_symlink_and_missing_token_fail_before_http(self):
        for receipt in (self.f.receipt, {**self.receipt, "producer": {**self.f.producer,
                "event": "local", "workflowPath": None, "runId": None, "runAttempt": None, "pullRequest": None}}):
            self.path.write_bytes(canonical_json_bytes(receipt))
            self.requests.clear()
            with self.assertRaises(ValueError):
                self.call()
            self.assertEqual([], self.requests)
        self.path.write_bytes(self.raw)
        with self.assertRaises(ValueError): self.call(token="")
        original = self.path.with_name("retained.json")
        self.path.rename(original)
        self.path.symlink_to(original)
        with self.assertRaises(ValueError): self.call()
        self.assertEqual(self.raw, original.read_bytes())

    def test_late_original_receipt_mutation_rejects_locator(self):
        window = locator.products._require_artifact_job_window
        def mutate(*args):
            window(*args)
            self.path.write_bytes(self.raw + b" ")
        with patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), self.assertRaisesRegex(ValueError, "receipt changed"):
            self.call()
        self.assertFalse(self.f.output.exists())


if __name__ == "__main__":
    unittest.main()

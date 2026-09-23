"""Official SDK Android validation locator; synthetic HTTP, no upload download."""

from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_android_original_upload_locator as locator
from ci.tests import test_sdk_facade_capture as facade_fixture
from ci.tests import test_runtime_aggregate_upload as transport_fixture
from products.inventory import canonical_json_bytes, sha256_bytes


class AndroidOriginalUploadLocatorTest(unittest.TestCase):
    component = "sdk-android"
    phase = "validation"
    targets = ("android",)
    required_directories = ("inputs", "originals", "stage")
    setUp = facade_fixture.FacadeCaptureTest.setUp
    select = facade_fixture.FacadeCaptureTest.select
    archive = transport_fixture.RuntimeAggregateUploadTest.archive
    api = transport_fixture.RuntimeAggregateUploadTest.api

    def call(self, *, listed=None, detail=None, **changes):
        requested = []

        def official(url, token):
            requested.append(url)
            if url.endswith("/actions/runs/71/artifacts?per_page=100&page=1"):
                return json.dumps({"artifacts": [self.artifact] if listed is None else listed}).encode()
            if url.endswith("/zip"):
                raise AssertionError("Locator must not download original upload bytes")
            if url.endswith("/actions/artifacts/701") and detail is not None:
                return json.dumps(detail).encode()
            return self.api(url, token)

        arguments = {"expected_receipt_sha256": sha256_bytes(self.receipt_bytes),
                     "trusted_workflow_sha": self.pin, "repository_root": self.root,
                     "environ": {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "99"},
                     "token": "synthetic-token"}
        arguments.update(changes)
        with patch.object(locator.products, "_validate_plan", return_value=self.plan), patch(
                "reuse.api_request", side_effect=official):
            result = getattr(locator, f"locate_sdk_android_{self.phase}_upload")(
                self.plan_path, self.receipt_path, **arguments)
        return result, requested

    def test_original_receipt_selects_official_job_upload_without_downloading_or_current_producer(self):
        before = (self.plan_path.read_bytes(), self.receipt_path.read_bytes())
        result, requested = self.call()
        self.assertEqual({"artifact_id": 701, "artifact_sha256": self.artifact["digest"]}, result)
        self.assertEqual(before, (self.plan_path.read_bytes(), self.receipt_path.read_bytes()))
        self.assertTrue(any("/actions/runs/71/attempts/2" in url for url in requested))
        self.assertTrue(any("/actions/runs/71/artifacts?" in url for url in requested))
        self.assertTrue(any("/actions/artifacts/701" in url for url in requested))
        self.assertFalse(any(url.endswith("/zip") for url in requested))

    def test_receipt_pin_phase_plan_and_signing_secret_fail_before_official_lookup(self):
        with self.assertRaisesRegex(ValueError, "independent caller selection"):
            self.call(expected_receipt_sha256="sha256:" + "0" * 64)
        original = self.receipt_path.read_bytes()
        other_phase = "metadata" if self.phase == "validation" else "validation"
        self.receipt_path.write_bytes(canonical_json_bytes({**self.receipt, "phase": other_phase}))
        try:
            with self.assertRaises(ValueError):
                self.call(expected_receipt_sha256=sha256_bytes(self.receipt_path.read_bytes()))
        finally:
            self.receipt_path.write_bytes(original)
        self.receipt_path.write_bytes(canonical_json_bytes({
            **self.receipt, "producer": {**self.receipt["producer"], "repository": "other/repository"}}))
        try:
            with patch.object(locator.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaisesRegex(ValueError, "fixed repository"):
                self.call(expected_receipt_sha256=sha256_bytes(self.receipt_path.read_bytes()))
            observe.assert_not_called()
        finally:
            self.receipt_path.write_bytes(original)
        self.plan["remoteBuildAuthorized"] = False
        with self.assertRaisesRegex(ValueError, "authorized"):
            self.call()
        self.plan["remoteBuildAuthorized"] = True
        with self.assertRaises(ValueError):
            self.call(environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"})

    def test_job_runner_detail_window_and_ambiguity_fail_closed(self):
        original = deepcopy((self.jobs, self.artifact, self.run))
        for case in ("runner", "job", "name", "expired", "run", "window", "detail", "workflow"):
            self.jobs, self.artifact, self.run = deepcopy(original)
            if case == "runner": self.jobs[0]["labels"] = ["wrong-runner"]
            elif case == "job": self.jobs[0]["conclusion"] = "failure"
            elif case == "name": self.artifact["name"] += "-other"
            elif case == "expired": self.artifact["expired"] = True
            elif case == "run": self.artifact["workflow_run"]["id"] = 99
            elif case == "window": self.artifact["created_at"] = "2026-09-11T10:30:01Z"
            elif case == "detail": self.artifact["archive_download_url"] += "-other"
            else: self.run["referenced_workflows"][0]["sha"] = "0" * 40
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
        self.jobs, self.artifact, self.run = deepcopy(original)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.call(listed=[self.artifact, deepcopy(self.artifact)])
        with self.assertRaisesRegex(ValueError, "detail"):
            self.call(detail={**self.artifact, "digest": "sha256:" + "0" * 64})


class AndroidMetadataOriginalUploadLocatorTest(AndroidOriginalUploadLocatorTest):
    phase = "metadata"
    required_directories = ("worker", "selection", "originals", "inputs")


if __name__ == "__main__":
    unittest.main()

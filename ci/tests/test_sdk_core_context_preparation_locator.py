"""Core context upload observation remains separate from release admission."""

from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from ci import sdk_core_context_preparation_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture
from ci.tests.product_chain_support import output, write_receipt
from products.inventory import sha256_bytes


class CorePreparationLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.receipt_path = self.f.work / "core-metadata-receipt.json"
        self.receipt = write_receipt(self.receipt_path, product="sdk", component="sdk-core",
            phase="metadata", target="common",
            outputs=[output("fixture", "outputs/example.bin", b"example")], upstream=[],
            context={"producer": self.f.producer}, version="0.8.0", version_identity="0.8.0")
        self.f.jobs[0]["name"] = "product-validation / sdk-core-metadata-common"
        self.f.artifact["name"] = ("codex-agent-sdk-core-context-preparation-"
            f"{self.receipt['buildKey'].removeprefix('sha256:')}-{self.f.producer['tree']}-attempt-2")
        self.listing = [deepcopy(self.f.artifact)]
        self.requests = []

    def api(self, url, token):
        self.requests.append(url)
        self.assertEqual("synthetic-token", token)
        if "/actions/runs/71/artifacts?" in url:
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator must not download evidence")
        return self.f.api(url, token)

    def call(self, **changes):
        arguments = {"expected_receipt_sha256": sha256_bytes(self.receipt_path.read_bytes()),
            "preparation_artifact_id": 701,
            "preparation_artifact_sha256": self.f.artifact["digest"],
            "trusted_workflow_sha": self.f.pin, "token": "synthetic-token",
            "environ": {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "9"}}
        with patch("reuse.api_request", side_effect=self.api):
            return locator.locate_core_context_preparation(self.receipt_path,
                **(arguments | changes))

    def test_fixed_original_job_and_exact_caller_outputs_only(self):
        self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]},
                         self.call())
        self.assertTrue(any("/runs/71/attempts/2" in url for url in self.requests))
        self.assertFalse(any("/runs/999" in url or url.endswith("/zip") for url in self.requests))

    def test_wrong_receipt_or_caller_pin_rejects(self):
        with patch.object(locator, "_locate") as observe, self.assertRaisesRegex(
                ValueError, "independent caller selection"):
            self.call(expected_receipt_sha256="sha256:" + "0" * 64)
        observe.assert_not_called()
        for change in ({"preparation_artifact_id": 702},
                       {"preparation_artifact_sha256": "sha256:" + "0" * 64}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call(**change)
        other = self.f.work / "other-receipt.json"
        write_receipt(other, product="sdk", component="sdk-core", phase="validation",
            target="jvm", outputs=[output("fixture", "outputs/example.bin", b"example")],
            upstream=[], context={"producer": self.f.producer}, version="0.8.0",
            version_identity="0.8.0")
        with patch.object(locator, "_locate") as observe, self.assertRaises(ValueError):
            locator.locate_core_context_preparation(other,
                expected_receipt_sha256=sha256_bytes(other.read_bytes()),
                preparation_artifact_id=701,
                preparation_artifact_sha256=self.f.artifact["digest"],
                trusted_workflow_sha=self.f.pin, token="synthetic-token", environ={})
        observe.assert_not_called()

    def test_official_job_and_upload_mutations_reject(self):
        baseline = deepcopy((self.f.run, self.f.jobs, self.f.artifact, self.f.commit))
        for mutation in ("failed", "wrong-job", "wrong-workflow", "wrong-tree", "expired", "ambiguous"):
            self.f.run, self.f.jobs, self.f.artifact, self.f.commit = deepcopy(baseline)
            self.listing = [deepcopy(self.f.artifact)]
            if mutation == "failed": self.f.jobs[0]["conclusion"] = "failure"
            elif mutation == "wrong-job": self.f.jobs[0]["name"] += "-other"
            elif mutation == "wrong-workflow": self.f.run["referenced_workflows"][0]["sha"] = "e" * 40
            elif mutation == "wrong-tree": self.f.commit["tree"]["sha"] = "e" * 40
            elif mutation == "expired": self.listing[0]["expired"] = True
            else: self.listing.append(deepcopy(self.f.artifact))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()


if __name__ == "__main__":
    unittest.main()

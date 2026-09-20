"""Receipt-first official metadata routing, never original content admission.

Real receipt and official metadata parsers run over synthetic mocked HTTP;
caller selection/authentication and full original replay remain separate gates.
"""

from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from ci import sdk_apple_upload_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture
from ci.tests.product_chain_support import output, write_receipt
from products.inventory import canonical_json_bytes


class OriginalAppleUploadLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.environment = {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "8", "GITHUB_SHA": "e" * 40,
                            "GITHUB_REPOSITORY": "different/current-repository"}
        self.requests = []
        self.receipts = {}
        for phase in ("binary", "package"):
            path = self.f.work / f"{phase}-receipt.json"
            value = write_receipt(path, product="sdk", component="sdk-ios", phase=phase, target="ios",
                outputs=[output("synthetic", "outputs/original.bin", b"synthetic fixture")], upstream=[],
                version="0.8.0", version_identity="0.8.0", context={"producer": self.f.producer})
            self.receipts[phase] = (path, value)
        self.configure("binary")

    def configure(self, phase):
        self.phase = phase
        self.receipt_path, self.receipt = self.receipts[phase]
        self.f.jobs[0]["name"] = f"product-validation / sdk-sdk-ios-{phase}-ios"
        self.f.artifact["name"] = (f"codex-agent-sdk-worker-sdk-ios-{phase}-ios-"
            f"{self.receipt['buildKey'].removeprefix('sha256:')}-{'b' * 40}-attempt-2")
        self.listing = [deepcopy(self.f.artifact)]

    def api(self, url, token):
        self.requests.append(url)
        if "/actions/runs/71/artifacts?" in url:
            self.assertEqual("synthetic-token", token)
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator must not download original product bytes")
        return self.f.api(url, token)

    def call(self, **changes):
        with patch("reuse.api_request", side_effect=self.api):
            return locator.locate_original_apple_upload(self.receipt_path, **{
                "trusted_workflow_sha": self.f.pin, "token": "synthetic-token",
                "environ": self.environment, **changes})

    def test_binary_and_package_use_exact_original_not_current_producer(self):
        for phase in self.receipts:
            self.configure(phase)
            raw = self.receipt_path.read_bytes()
            self.listing += [{**self.f.artifact, "id": 702, "expired": True},
                             {**self.f.artifact, "id": 703, "name": self.f.artifact["name"].replace("attempt-2", "attempt-8")}]
            self.requests.clear()
            with self.subTest(phase=phase), patch.object(locator.products, "_consumer", side_effect=AssertionError("must not elect current producer")), \
                    patch.object(locator.products, "_validate_plan", side_effect=AssertionError("must not replay current plan")):
                self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
            self.assertTrue(any("/runs/71/attempts/2" in url for url in self.requests))
            self.assertFalse(any("/runs/999" in url for url in self.requests))
            self.assertEqual(1, sum("/runs/71/artifacts?" in url for url in self.requests))
            self.assertEqual(raw, self.receipt_path.read_bytes())

    def test_missing_duplicate_expired_or_wrong_key_attempt_tree_never_falls_back(self):
        baseline = deepcopy(self.f.artifact)
        for mutation in ("missing", "duplicate", "expired", "key", "attempt", "tree", "id", "digest"):
            self.listing = [deepcopy(baseline)]
            if mutation == "missing": self.listing = []
            elif mutation == "duplicate": self.listing.append(deepcopy(baseline))
            elif mutation == "expired": self.listing[0]["expired"] = True
            elif mutation == "key": self.listing[0]["name"] = baseline["name"].replace(
                self.receipt["buildKey"].removeprefix("sha256:"), "d" * 64)
            elif mutation == "attempt": self.listing[0]["name"] = baseline["name"].replace("attempt-2", "attempt-8")
            elif mutation == "tree": self.listing[0]["name"] = baseline["name"].replace("b" * 40, "e" * 40)
            elif mutation == "id": self.listing[0]["id"] = True
            else: self.listing[0]["digest"] = "bad"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()

    def test_official_job_pin_run_detail_and_window_checks_remain_mandatory(self):
        baseline = deepcopy((self.f.run, self.f.jobs, self.f.artifact))
        for mutation in ("job", "failed", "pin", "attempt", "run", "head", "window", "detail", "url"):
            self.f.run, self.f.jobs, self.f.artifact = deepcopy(baseline)
            if mutation == "job": self.f.jobs[0]["name"] += "-other"
            elif mutation == "failed": self.f.jobs[0]["conclusion"] = "failure"
            elif mutation == "pin": self.f.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif mutation == "attempt": self.f.run["run_attempt"] = 1
            elif mutation == "run": self.f.artifact["workflow_run"]["id"] = 999
            elif mutation == "head": self.f.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif mutation == "window": self.f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif mutation == "url": self.f.artifact["archive_download_url"] = "https://elsewhere.invalid/archive"
            self.listing = [deepcopy(self.f.artifact)]
            if mutation == "detail": self.f.artifact["digest"] = "sha256:" + "d" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()

    def test_noncanonical_malformed_or_non_ios_binary_package_receipts_fail_before_http(self):
        raw = self.receipt_path.read_bytes()
        for field, value in (("product", "runtime"), ("component", "javascript"),
                             ("phase", "validation"), ("target", "ios-arm64"),
                             ("schemaVersion", True), ("buildKey", "sha256:" + "0" * 64)):
            self.receipt_path.write_bytes(canonical_json_bytes({**self.receipt, field: value}))
            with self.subTest(field=field), patch.object(locator.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
        for invalid in (json.dumps(self.receipt, indent=2).encode(), b'{"schemaVersion":1,"schemaVersion":1}\n'):
            self.receipt_path.write_bytes(invalid)
            with self.assertRaises(ValueError):
                self.call()
        self.receipt_path.write_bytes(raw)

    def test_no_secret_entry_and_exit_and_no_empty_token(self):
        for live in (False, True):
            selected = os.environ if live else self.environment
            selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            try:
                with patch.object(locator, "read_regular_file_bytes") as read, self.assertRaises(ValueError):
                    self.call()
                read.assert_not_called()
            finally:
                del selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]
        with patch.object(locator, "read_regular_file_bytes") as read, self.assertRaises(ValueError):
            self.call(token="")
        read.assert_not_called()
        gate = locator.products._require_artifact_job_window
        def mutate(*args):
            gate(*args)
            self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
        with patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), self.assertRaises(ValueError):
            self.call()

    def test_original_raw_and_parsed_receipt_mutations_reject_but_current_run_changes_do_not_relabel(self):
        raw = self.receipt_path.read_bytes()
        validate = locator.products.validate_phase_receipt
        gate = locator.products._require_artifact_job_window
        for selected in ("raw", "parsed", "current-environment"):
            self.receipt_path.write_bytes(raw)
            parsed = []
            def receipt(value):
                result = validate(value)
                parsed.append(result)
                return result
            def mutate(*args):
                gate(*args)
                if selected == "raw": self.receipt_path.write_bytes(raw + b" ")
                elif selected == "parsed": parsed[0]["productVersion"] = "0.9.0"
                else: self.environment["GITHUB_RUN_ID"] = "1000"
            with self.subTest(selected=selected), patch.object(locator.products, "validate_phase_receipt", side_effect=receipt), \
                    patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate):
                if selected == "current-environment":
                    self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
                else:
                    with self.assertRaisesRegex(ValueError, "changed during observation"):
                        self.call()


if __name__ == "__main__":
    unittest.main()

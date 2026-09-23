"""Core original locators over synthetic official API responses; no network."""

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_facade_upload_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture
from ci.tests.product_chain_support import output, write_receipt
from products.inventory import canonical_json_bytes, sha256_bytes
from products.registry import SDK_FACADE_TARGETS
from sdk_facade_capture import _capture_route


class CoreUploadLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.environment = {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "9"}
        self.requests = []
        self.select("validation", "jvm")

    def select(self, phase, target, component="sdk-core"):
        self.receipt_path = self.f.work / f"{component}-{phase}-{target}.json"
        self.receipt = write_receipt(self.receipt_path, product="sdk", component=component,
            phase=phase, target=target,
            outputs=[output("fixture", "outputs/example.bin", b"example")], upstream=[],
            context={"producer": self.f.producer}, version="0.8.0", version_identity="0.8.0")
        _, _, _, job, name, _ = _capture_route(self.receipt)
        self.f.jobs[0]["name"] = job
        self.f.artifact["name"] = name
        self.listing = [deepcopy(self.f.artifact)]

    def api(self, url, token):
        self.requests.append(url)
        self.assertEqual("synthetic-token", token)
        if "/actions/runs/71/artifacts?" in url:
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator must not download product bytes")
        return self.f.api(url, token)

    def call(self, **changes):
        with patch("reuse.api_request", side_effect=self.api):
            return locator.locate_original_facade_upload(self.receipt_path, **{
                "expected_receipt_sha256": sha256_bytes(self.receipt_path.read_bytes()),
                "trusted_workflow_sha": self.f.pin, "token": "synthetic-token",
                "environ": self.environment, **changes})

    def call_maven(self, **changes):
        with patch("reuse.api_request", side_effect=self.api):
            return locator.locate_original_maven_upload(self.receipt_path, **{
                "expected_receipt_sha256": sha256_bytes(self.receipt_path.read_bytes()),
                "trusted_workflow_sha": self.f.pin, "token": "synthetic-token",
                "environ": self.environment, **changes})

    def test_maven_binary_and_package_use_only_original_fixed_routes(self):
        for component, target in (("sdk-core", "common"), ("sdk-android", "android")):
            for phase in ("binary", "package"):
                with self.subTest(component=component, phase=phase):
                    self.select(phase, target, component)
                    self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]},
                                     self.call_maven())
        self.assertFalse(any("/runs/999" in url or url.endswith("/zip") for url in self.requests))
        self.select("validation", "jvm")
        with patch.object(locator, "_locate") as observe, self.assertRaises(ValueError):
            self.call_maven()
        observe.assert_not_called()

    def test_maven_requires_independently_pinned_receipt_and_official_upload(self):
        self.select("binary", "common")
        with patch.object(locator, "_locate") as observe, self.assertRaisesRegex(
                ValueError, "independent caller selection"):
            self.call_maven(expected_receipt_sha256="sha256:" + "0" * 64)
        observe.assert_not_called()
        self.listing = []
        with self.assertRaises(ValueError):
            self.call_maven()

    def test_maven_cli_selects_only_the_maven_locator(self):
        self.select("binary", "common")
        output = io.StringIO()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True), \
                patch.object(locator, "locate_original_maven_upload", return_value={
                    "artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}) as maven, \
                patch.object(locator, "locate_original_facade_upload") as facade, redirect_stdout(output):
            self.assertEqual(0, locator.main(["--maven", "--receipt", str(self.receipt_path),
                "--expected-receipt-sha256", sha256_bytes(self.receipt_path.read_bytes()),
                "--trusted-workflow-sha", self.f.pin]))
        self.assertEqual(701, json.loads(output.getvalue())["artifact_id"])
        self.assertEqual("synthetic-token", maven.call_args.kwargs["token"])
        facade.assert_not_called()

    def test_independent_selected_receipt_digest_is_required_before_official_observation(self):
        with patch.object(locator, "_locate") as observe, self.assertRaisesRegex(
                ValueError, "independent caller selection"):
            self.call(expected_receipt_sha256="sha256:" + "0" * 64)
        observe.assert_not_called()
        with patch.object(locator, "_locate") as observe, self.assertRaises(ValueError):
            self.call(expected_receipt_sha256="not-a-digest")
        observe.assert_not_called()

    def test_all_eleven_validation_targets_and_metadata_use_fixed_original_routes(self):
        with patch.object(locator.products, "_consumer", side_effect=AssertionError("current run is not authority")):
            for phase, target in (("validation", value) for value in SDK_FACADE_TARGETS):
                with self.subTest(phase=phase, target=target):
                    self.select(phase, target)
                    self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
            self.select("metadata", "common")
            self.assertEqual(701, self.call()["artifact_id"])
        self.assertFalse(any("/runs/999" in url for url in self.requests))
        self.assertTrue(any("/runs/71/attempts/2" in url for url in self.requests))

    def test_missing_ambiguous_expired_or_wrong_identity_rejects(self):
        original = deepcopy(self.f.artifact)
        for change in ("missing", "ambiguous", "expired", "key", "attempt", "tree", "id", "digest"):
            self.f.artifact = deepcopy(original)
            self.listing = [deepcopy(original)]
            if change == "missing": self.listing = []
            elif change == "ambiguous": self.listing.append(deepcopy(original))
            elif change == "expired": self.listing[0]["expired"] = True
            elif change == "key": self.listing[0]["name"] = original["name"].replace(
                self.receipt["buildKey"].removeprefix("sha256:"), "d" * 64)
            elif change == "attempt": self.listing[0]["name"] = original["name"].replace("attempt-2", "attempt-9")
            elif change == "tree": self.listing[0]["name"] = original["name"].replace("b" * 40, "d" * 40)
            elif change == "id": self.listing[0]["id"] = True
            else: self.listing[0]["digest"] = "invalid"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_official_job_run_detail_and_window_must_match(self):
        baseline = deepcopy((self.f.run, self.f.jobs, self.f.artifact))
        for change in ("job", "failed", "pin", "attempt", "run", "head", "window", "detail", "url"):
            self.f.run, self.f.jobs, self.f.artifact = deepcopy(baseline)
            if change == "job": self.f.jobs[0]["name"] += "-wrong"
            elif change == "failed": self.f.jobs[0]["conclusion"] = "failure"
            elif change == "pin": self.f.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif change == "attempt": self.f.run["run_attempt"] = 1
            elif change == "run": self.f.artifact["workflow_run"]["id"] = 999
            elif change == "head": self.f.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif change == "window": self.f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif change == "url": self.f.artifact["archive_download_url"] = "https://elsewhere.invalid/zip"
            self.listing = [deepcopy(self.f.artifact)]
            if change == "detail": self.f.artifact["digest"] = "sha256:" + "d" * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.call()

    def test_wrong_receipt_identity_and_mutation_fail_before_or_after_observation(self):
        raw = self.receipt_path.read_bytes()
        for change in ({"component": "sdk-ios"}, {"phase": "package"}, {"target": "invalid"}):
            self.receipt_path.write_bytes(canonical_json_bytes({**self.receipt, **change}))
            with patch.object(locator, "_locate") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
        wrong_producer = {**self.receipt, "producer": {**self.receipt["producer"], "runId": 72}}
        self.receipt_path.write_bytes(canonical_json_bytes(wrong_producer))
        with self.assertRaisesRegex(AssertionError, "/runs/72/attempts/2"):
            self.call()  # The mock permits only run 71; no current-run fallback.
        self.receipt_path.write_bytes(raw)
        gate = locator.products._require_artifact_job_window
        for change in ("raw", "parsed", "secret"):
            self.receipt_path.write_bytes(raw)
            validated = []
            original_validate = locator.products.validate_phase_receipt
            def validate(value):
                result = original_validate(value)
                validated.append(result)
                return result
            def mutate(*args):
                gate(*args)
                if change == "raw": self.receipt_path.write_bytes(raw + b" ")
                elif change == "parsed": validated[0]["productVersion"] = "0.9.0"
                else: self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            with self.subTest(change=change), patch.object(locator.products, "validate_phase_receipt", side_effect=validate), \
                    patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), self.assertRaises(ValueError):
                self.call()
            self.environment.pop("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", None)
        self.receipt_path.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()

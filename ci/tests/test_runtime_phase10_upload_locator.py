"""Official aggregate upload election with mocked CI, not release admission."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ci import runtime_phase10_upload_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture


class RuntimePhase10UploadLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.listing = [deepcopy(self.f.artifact)]
        self.environment = {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"}
        environment = patch.dict("os.environ", {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def api(self, url, token):
        if "/actions/runs/71/artifacts?" in url:
            self.assertEqual("synthetic-token", token)
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator must not download release bytes")
        return self.f.api(url, token)

    def call(self, **changes):
        with patch.object(locator.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return locator.locate_runtime_phase10_upload(self.f.plan_path, self.f.root, **{
                "trusted_workflow_sha": self.f.pin, "environ": self.environment,
                "token": "synthetic-token", **changes,
            })

    def test_exact_current_successful_upload_only(self):
        self.listing.extend(({**self.f.artifact, "name": "unrelated", "id": 702},
                             {**self.f.artifact, "id": 703, "expired": True}))
        self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
        self.assertFalse(self.f.output.exists())

    def test_official_selection_captures_exact_original_bytes(self):
        with patch.object(locator.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api), \
                patch.object(locator.products, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs:
                        destination.write_bytes(self.f.raw)):
            transport = locator.capture_observed_runtime_phase10_upload(
                self.f.plan_path, self.f.root, self.f.output,
                trusted_workflow_sha=self.f.pin, expected_build_key=self.f.key,
                expected_metadata_receipt_sha256=self.f.digest,
                environ=self.environment, token="synthetic-token",
            )
        self.assertEqual(701, transport["artifact"]["id"])
        self.assertEqual(self.f.raw, (self.f.output / "transport.zip").read_bytes())
        self.assertEqual(self.f.files["caller.json"],
                         (self.f.output / "original/caller.json").read_bytes())

    def test_wrong_or_ambiguous_upload_and_observation_reject(self):
        original = deepcopy((self.f.run, self.f.jobs, self.f.artifact))
        for mutation in ("missing", "duplicate", "expired", "wrong-attempt", "bad-digest",
                         "missing-size", "wrong-size", "wrong-head", "bad-window", "failed-job", "wrong-workflow"):
            self.f.run, self.f.jobs, self.f.artifact = deepcopy(original)
            self.listing = [deepcopy(self.f.artifact)]
            if mutation == "missing": self.listing = []
            elif mutation == "duplicate": self.listing.append(deepcopy(self.f.artifact))
            elif mutation == "expired": self.listing[0]["expired"] = True
            elif mutation == "wrong-attempt": self.listing[0]["name"] += "-wrong"
            elif mutation == "bad-digest": self.listing[0]["digest"] = "not-sha256"
            elif mutation == "missing-size": del self.listing[0]["size_in_bytes"]
            elif mutation == "wrong-size": self.f.artifact["size_in_bytes"] += 1
            elif mutation == "wrong-head": self.f.artifact["workflow_run"]["head_sha"] = "d" * 40
            elif mutation == "bad-window": self.f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif mutation == "failed-job": self.f.jobs[0]["conclusion"] = "failure"
            else: self.f.run["referenced_workflows"][0]["sha"] = "d" * 40
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()

    def test_scope_secret_and_plan_mutation_reject(self):
        for changed in ({"remoteBuildAuthorized": False}, {"event": "workflow_dispatch"}):
            self.f.plan.update(changed)
            with patch.object(locator.products, "_observe_ci_producer_jobs") as observer, \
                    self.assertRaises(ValueError):
                self.call()
            observer.assert_not_called()
            self.f.plan.update(remoteBuildAuthorized=True, event="pull_request")
        with patch.object(locator.products, "_observe_ci_producer_jobs") as observer, \
                self.assertRaises(ValueError):
            self.call(environ={**self.environment, "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"})
        observer.assert_not_called()
        window = locator.products._require_artifact_job_window
        def mutate(*args):
            window(*args)
            self.f.plan_path.write_bytes(b"changed")
        with patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), \
                self.assertRaises(ValueError):
            self.call()

    def test_cli_requires_reviewed_workflow_pin(self):
        with patch.dict(locator.os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True), \
                self.assertRaises(SystemExit) as error:
            locator.main(["--plan", str(self.f.plan_path), "--candidate-root", str(self.f.root)])
        self.assertEqual(2, error.exception.code)

    def test_cli_capture_requires_complete_independent_pins(self):
        base = ["--plan", str(self.f.plan_path), "--candidate-root", str(self.f.root),
                "--trusted-workflow-sha", self.f.pin, "--destination", str(self.f.output)]
        with patch.dict(locator.os.environ, {"GITHUB_TOKEN": "synthetic-token",
                                          **self.environment}, clear=True), \
                self.assertRaises(SystemExit) as error:
            locator.main(base)
        self.assertEqual(2, error.exception.code)
        self.assertFalse(self.f.output.exists())
        with patch.dict(locator.os.environ, {"GITHUB_TOKEN": "synthetic-token",
                                          **self.environment}, clear=True), \
                patch.object(locator.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api), \
                patch.object(locator.products, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs:
                        destination.write_bytes(self.f.raw)):
            self.assertEqual(0, locator.main(base + [
                "--expected-build-key", self.f.key,
                "--expected-metadata-receipt-sha256", self.f.digest,
            ]))
        self.assertEqual(self.f.raw, (self.f.output / "transport.zip").read_bytes())


if __name__ == "__main__":
    unittest.main()

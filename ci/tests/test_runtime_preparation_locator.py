"""Real original CI metadata gates with mocked HTTP/plan; no upload admission."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_upload as fixture
from ci import runtime_preparation_locator as locator


class RuntimePreparationLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.environment = {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"}
        self.configure("linux-x64")
        self.requests = []
        environment = patch.dict("os.environ", {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def configure(self, target):
        self.target = target
        self.f.jobs[0]["name"] = f"product-validation / runtime-signing-prepare-{target}"
        self.f.artifact["name"] = f"codex-agent-runtime-signing-preparation-{target}-{'b' * 40}-attempt-2"
        self.listing = [deepcopy(self.f.artifact)]

    def api(self, url, token):
        self.requests.append(url)
        if "/actions/runs/71/artifacts?" in url:
            self.assertEqual("synthetic-token", token)
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator must not download product bytes")
        return self.f.api(url, token)

    def call(self, **changes):
        with patch.object(locator.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return locator.locate_runtime_signing_preparation(self.f.plan_path, self.f.root, **{
                "target": self.target, "trusted_workflow_sha": self.f.pin,
                "environ": self.environment, "token": "synthetic-token", **changes})

    def test_all_six_fixed_jobs_return_only_exact_current_upload_locator(self):
        for target in (*locator.NATIVE_TARGETS, "aggregate"):
            self.configure(target)
            self.listing += [{**self.f.artifact, "name": "unrelated", "id": 702},
                             {**self.f.artifact, "expired": True, "id": 703}]
            self.requests.clear()
            with self.subTest(target=target):
                self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
                self.assertEqual(1, sum("/actions/runs/71/artifacts?" in url for url in self.requests))
                self.assertEqual(1, sum(url.endswith("/actions/artifacts/701") for url in self.requests))
                self.assertFalse(self.f.output.exists())

    def test_missing_ambiguous_wrong_attempt_expired_or_malformed_locator_rejects(self):
        original = deepcopy(self.f.artifact)
        for mutation in ("missing", "duplicate", "attempt", "expired", "id", "digest"):
            self.listing = [deepcopy(original)]
            if mutation == "missing": self.listing = []
            elif mutation == "duplicate": self.listing.append(deepcopy(original))
            elif mutation == "attempt": self.listing[0]["name"] = original["name"].replace("attempt-2", "attempt-1")
            elif mutation == "expired": self.listing[0]["expired"] = True
            elif mutation == "id": self.listing[0]["id"] = True
            else: self.listing[0]["digest"] = "not-sha256"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()

    def test_observer_run_job_pin_window_and_detail_pairing_fail_closed(self):
        baseline = deepcopy((self.f.run, self.f.jobs, self.f.artifact))
        for mutation in ("attempt", "job", "failed", "pin", "run", "head", "window", "no-window", "detail", "url"):
            self.f.run, self.f.jobs, self.f.artifact = deepcopy(baseline)
            if mutation == "attempt": self.f.run["run_attempt"] = 1
            elif mutation == "job": self.f.jobs[0]["name"] += "-other"
            elif mutation == "failed": self.f.jobs[0]["conclusion"] = "failure"
            elif mutation == "pin": self.f.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif mutation == "run": self.f.artifact["workflow_run"]["id"] = 72
            elif mutation == "head": self.f.artifact["workflow_run"]["head_sha"] = "d" * 40
            elif mutation == "window": self.f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif mutation == "no-window": del self.f.artifact["created_at"]
            elif mutation == "url": self.f.artifact["archive_download_url"] = "https://elsewhere.invalid/archive"
            self.listing = [deepcopy(self.f.artifact)]
            if mutation == "detail": self.f.artifact["digest"] = "sha256:" + "f" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()

    def test_denied_scope_secret_or_mutated_plan_never_yields_locator(self):
        for changes in ({"target": "javascript"}, {"token": ""},
                        {"environ": {**self.environment, "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}}):
            with self.subTest(changes=changes), patch.object(locator.products, "_observe_ci_producer_jobs") as observer, \
                    self.assertRaises(ValueError):
                self.call(**changes)
            observer.assert_not_called()
        for event, authorized in (("workflow_dispatch", True), ("pull_request", False)):
            self.f.plan.update(event=event, remoteBuildAuthorized=authorized)
            with patch.object(locator.products, "_observe_ci_producer_jobs") as observer, self.assertRaises(ValueError):
                self.call()
            observer.assert_not_called()
        self.f.plan.update(event="pull_request", remoteBuildAuthorized=True)
        window = locator.products._require_artifact_job_window
        def mutate(*args):
            window(*args)
            self.f.plan_path.write_bytes(b"changed original plan")
        with patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), self.assertRaises(ValueError):
            self.call()

    def test_strict_cli_forwarding_and_output_only_after_success(self):
        output = self.f.work / "github-output"
        argv = ["--plan", str(self.f.plan_path), "--candidate-root", str(self.f.root), "--target", "aggregate",
            "--trusted-workflow-sha", self.f.pin, "--github-output", str(output)]
        value = {"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}
        with patch.dict(locator.os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True), \
                patch.object(locator, "locate_runtime_signing_preparation", return_value=value) as locate:
            self.assertEqual(0, locator.main(argv))
            locate.assert_called_once_with(self.f.plan_path, self.f.root, target="aggregate",
                trusted_workflow_sha=self.f.pin, environ=locator.os.environ, token="synthetic-token")
        self.assertEqual({"artifact_id": "701", "artifact_sha256": self.f.artifact["digest"]},
            dict(line.split("=", 1) for line in output.read_text().splitlines()))
        for change in (argv[:-2] + ["--github-output", str(output.parent / "failed")],
                       argv + ["--command", "arbitrary"], argv + ["--trusted-workflow", self.f.pin]):
            with patch.dict(locator.os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True), \
                    patch.object(locator, "locate_runtime_signing_preparation", side_effect=ValueError("rejected")), \
                    self.assertRaises(SystemExit) as error:
                locator.main(change)
            self.assertEqual(2, error.exception.code)
        self.assertFalse((output.parent / "failed").exists())


if __name__ == "__main__":
    unittest.main()

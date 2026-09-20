"""Real fixed official metadata checks; mocked HTTP and plan/Git authority.

No product bytes are downloaded, and no receipt, host or semantic acceptance is
claimed. Fixture helpers are delegated, never inherited as unrelated tests.
"""

from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
import os
import unittest
from unittest.mock import patch

from ci import sdk_apple_upload_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture


class AppleUploadLocatorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.environment = {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"}
        self.key = "sha256:" + "d" * 64
        self.requests = []
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.configure("validation", "ios-arm64")

    def configure(self, mode, target):
        self.mode, self.target = mode, target
        if mode == "validation":
            self.f.jobs[0]["name"] = f"product-validation / sdk-sdk-ios-validation-{target}"
            name = f"codex-agent-sdk-worker-sdk-ios-validation-{target}-{'d' * 64}-{'b' * 40}-attempt-2"
        else:
            self.f.jobs[0]["name"] = f"product-validation / sdk-apple-signing-prepare-{target}"
            name = f"codex-agent-sdk-apple-signing-preparation-{target}-{'b' * 40}-attempt-2"
        self.f.artifact["name"] = name
        self.listing = [deepcopy(self.f.artifact)]

    def api(self, url, token):
        self.requests.append(url)
        if "/actions/runs/71/artifacts?" in url:
            self.assertEqual("synthetic-token", token)
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator cannot download product bytes")
        return self.f.api(url, token)

    def call(self, **changes):
        with patch.object(locator.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return locator.locate_apple_upload(self.f.plan_path, self.f.root, **{
                "mode": self.mode, "target": self.target, "trusted_workflow_sha": self.f.pin,
                **({"expected_build_key": self.key} if self.mode == "validation" else {}),
                "environ": self.environment, "token": "synthetic-token", **changes})

    def test_both_modes_and_targets_return_only_exact_current_locator_without_downloads(self):
        plan_bytes = self.f.plan_path.read_bytes()
        for mode in ("validation", "preparation"):
            for target in ("ios-arm64", "ios-simulator-arm64"):
                self.configure(mode, target)
                self.listing += [{**self.f.artifact, "name": "unrelated", "id": 702},
                                 {**self.f.artifact, "expired": True, "id": 703}]
                self.requests.clear()
                with self.subTest(mode=mode, target=target):
                    self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
                    self.assertEqual(1, sum("/actions/runs/71/artifacts?" in url for url in self.requests))
                    self.assertEqual(1, sum(url.endswith("/actions/artifacts/701") for url in self.requests))
                    self.assertEqual(plan_bytes, self.f.plan_path.read_bytes())
                    self.assertFalse(self.f.output.exists())

    def test_missing_ambiguous_expired_wrong_attempt_key_and_malformed_metadata_reject(self):
        for mode in ("validation", "preparation"):
            self.configure(mode, "ios-arm64")
            original = deepcopy(self.f.artifact)
            for mutation in ("missing", "duplicate", "attempt", "tree", "expired", "id", "digest", "name"):
                self.listing = [deepcopy(original)]
                if mutation == "missing": self.listing = []
                elif mutation == "duplicate": self.listing.append(deepcopy(original))
                elif mutation == "attempt": self.listing[0]["name"] = original["name"].replace("attempt-2", "attempt-1")
                elif mutation == "tree": self.listing[0]["name"] = original["name"].replace("b" * 40, "e" * 40)
                elif mutation == "expired": self.listing[0]["expired"] = True
                elif mutation == "id": self.listing[0]["id"] = True
                elif mutation == "digest": self.listing[0]["digest"] = "not-sha256"
                else: self.listing[0]["name"] += "-wrong"
                with self.subTest(mode=mode, mutation=mutation), self.assertRaises(ValueError):
                    self.call()
        self.configure("validation", "ios-arm64")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.call(expected_build_key="sha256:" + "e" * 64)

    def test_observed_job_run_pin_window_and_detail_disagreement_fail_closed(self):
        baseline = deepcopy((self.f.run, self.f.jobs, self.f.artifact, self.f.commit))
        for mutation in ("attempt", "job", "failed", "pin", "tree", "run", "head", "window", "no-window", "detail", "url"):
            self.f.run, self.f.jobs, self.f.artifact, self.f.commit = deepcopy(baseline)
            if mutation == "attempt": self.f.run["run_attempt"] = 1
            elif mutation == "job": self.f.jobs[0]["name"] += "-other"
            elif mutation == "failed": self.f.jobs[0]["conclusion"] = "failure"
            elif mutation == "pin": self.f.run["referenced_workflows"][0]["sha"] = "e" * 40
            elif mutation == "tree": self.f.commit["tree"]["sha"] = "e" * 40
            elif mutation == "run": self.f.artifact["workflow_run"]["id"] = 72
            elif mutation == "head": self.f.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif mutation == "window": self.f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif mutation == "no-window": del self.f.artifact["created_at"]
            elif mutation == "url": self.f.artifact["archive_download_url"] = "https://elsewhere.invalid/archive"
            self.listing = [deepcopy(self.f.artifact)]
            if mutation == "detail": self.f.artifact["digest"] = "sha256:" + "f" * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call()

    def test_invalid_modes_scope_keys_and_denied_plan_fail_before_observation(self):
        changes = ({"mode": "sign"}, {"target": "ios"}, {"token": ""},
                   {"expected_build_key": None}, {"expected_build_key": "HEAD"},
                   {"mode": "preparation", "expected_build_key": self.key})
        for change in changes:
            with self.subTest(change=change), patch.object(locator.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**change)
            observe.assert_not_called()
        for event, authorized in (("workflow_dispatch", True), ("pull_request", False)):
            self.f.plan.update(event=event, remoteBuildAuthorized=authorized)
            with patch.object(locator.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()

    def test_secret_guard_precedes_reads_and_rechecks_presence_after_observation(self):
        for live in (False, True):
            selected = os.environ if live else self.environment
            for value in ("", "opaque secret"):
                selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = value
                try:
                    with patch.object(locator, "read_regular_file_bytes") as read, self.assertRaises(ValueError):
                        self.call()
                    read.assert_not_called()
                finally:
                    del selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]
        gate = locator.products._require_artifact_job_window
        def mutate(*args):
            gate(*args)
            self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
        with patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "signing-secret context"):
            self.call()

    def test_original_private_plan_and_current_environment_mutation_never_yield_locator(self):
        gate = locator.products._require_artifact_job_window
        raw = self.f.plan_path.read_bytes()
        for selected in ("original", "private", "parsed", "environment"):
            self.f.plan_path.write_bytes(raw)
            self.environment["GITHUB_RUN_ATTEMPT"] = "2"
            self.f.plan = json.loads(raw)
            captured = []
            def validate(path, root):
                captured.append(path)
                return self.f.plan
            def mutate(*args):
                gate(*args)
                if selected == "environment": self.environment["GITHUB_RUN_ATTEMPT"] = "3"
                elif selected == "parsed": self.f.plan["remoteBuildAuthorized"] = False
                else: (self.f.plan_path if selected == "original" else captured[0]).write_bytes(b"changed")
            with self.subTest(selected=selected), \
                    patch.object(locator.products, "_validate_plan", side_effect=validate), \
                    patch("reuse.api_request", side_effect=self.api), \
                    patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "changed during observation"):
                locator.locate_apple_upload(self.f.plan_path, self.f.root, mode="validation", target=self.target,
                    trusted_workflow_sha=self.f.pin, expected_build_key=self.key, environ=self.environment, token="synthetic-token")

    def test_strict_cli_mode_forwarding_and_no_output_on_errors(self):
        value = {"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}
        for mode in ("validation", "preparation"):
            output = self.f.work / f"github-output-{mode}"
            argv = [mode, "--plan", str(self.f.plan_path), "--candidate-root", str(self.f.root),
                    "--target", "ios-arm64", "--trusted-workflow-sha", self.f.pin,
                    "--github-output", str(output)]
            if mode == "validation": argv += ["--expected-build-key", self.key]
            with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True), \
                    patch.object(locator, "locate_apple_upload", return_value=value) as locate:
                self.assertEqual(0, locator.main(argv))
                locate.assert_called_once_with(self.f.plan_path, self.f.root, mode=mode, target="ios-arm64",
                    trusted_workflow_sha=self.f.pin, environ=os.environ, token="synthetic-token",
                    **({"expected_build_key": self.key} if mode == "validation" else {}))
            self.assertEqual({"artifact_id": "701", "artifact_sha256": self.f.artifact["digest"]},
                dict(line.split("=", 1) for line in output.read_text().splitlines()))
            invalid = [argv + ["--job", "arbitrary"], argv + ["--trusted-workflow", self.f.pin],
                       argv[:-2] if mode == "validation" else argv + ["--expected-build-key", self.key]]
            for arguments in invalid:
                with patch.object(locator, "locate_apple_upload") as locate, redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as error:
                    locator.main(arguments)
                self.assertEqual(2, error.exception.code)
                locate.assert_not_called()
        failed = self.f.work / "failed-output"
        argv = ["preparation", "--plan", str(self.f.plan_path), "--candidate-root", str(self.f.root),
                "--target", "ios-arm64", "--trusted-workflow-sha", self.f.pin, "--github-output", str(failed)]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True), \
                patch.object(locator, "locate_apple_upload", side_effect=ValueError("rejected")), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            locator.main(argv)
        self.assertFalse(failed.exists())


if __name__ == "__main__":
    unittest.main()
